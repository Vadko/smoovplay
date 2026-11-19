"""TensorRT backend for the RIFE flow network (FastIFNet): same math, faster kernels.

The PyTorch fp16 forward is exported to ONNX and built as a *strongly typed* engine, so TensorRT keeps
PyTorch's precision exactly (convolutions fp16, warps and blending fp32) instead of choosing its own.
Engines are built once per model / resolution / flow scale / GPU / TensorRT version (a minute or two)
and cached in models/trt/. They run on PyTorch's current CUDA stream, so they work inside the
interpolator's CUDA graphs.

TensorRT may be installed outside the venv (it's ~3 GB); if so, set FRAMEGEN_TRT_PATH to that folder.
"""
from __future__ import annotations

import hashlib
import os
import sys
import time
from pathlib import Path

import torch

from .fastrife import FastIFNet

TRT_PATH = os.environ.get("FRAMEGEN_TRT_PATH", "")
ENGINE_DIR = Path(__file__).resolve().parent.parent / "models" / "trt"


def import_trt():
    if TRT_PATH and os.path.isdir(TRT_PATH) and TRT_PATH not in sys.path:
        sys.path.append(TRT_PATH)  # appended, so it never shadows the venv's own packages
    import tensorrt as trt
    return trt


_available: bool | None = None


def trt_available() -> bool:
    """Whether TensorRT can be imported (cached)."""
    global _available
    if _available is None:
        try:
            import_trt()
            _available = True
        except Exception:  # noqa: BLE001 - missing or broken install: use PyTorch
            _available = False
    return _available


def auto_engine(scale: float) -> str:
    """What the "Auto" engine setting runs at a flow scale: TensorRT at full motion detail, where it's faster (7.9 vs
    9.0 ms per 1080p in-between frame on an RTX 4070 Ti SUPER), PyTorch at half, where PyTorch is (5.5 vs 6.8 ms)."""
    return "trt" if scale >= 1.0 and trt_available() else "torch"


class _Export(torch.nn.Module):
    """FastIFNet as an nn.Module with the timestep as an input, for torch.onnx.export."""

    def __init__(self, fast: FastIFNet) -> None:
        super().__init__()
        self.fast = fast
        self.blocks = torch.nn.ModuleList(fast.blocks)  # registers the weights

    def forward(self, src0: torch.Tensor, src1: torch.Tensor, t: torch.Tensor) -> torch.Tensor:
        return self.fast(src0, src1, t)


class TrtIFNet:
    """Drop-in for FastIFNet.__call__ on fixed-size [img | features] inputs."""

    def __init__(self, fast: FastIFNet, src_shape: tuple, tag: str, device: torch.device, build: bool = True) -> None:
        """build=False: raise FileNotFoundError instead of building an engine that isn't cached yet."""
        trt = import_trt()
        self.trt = trt
        self.logger = trt.Logger(trt.Logger.WARNING)
        gpu = torch.cuda.get_device_name(device)
        key = hashlib.sha1(f"{tag}|{tuple(src_shape)}|{gpu}|{trt.__version__}".encode()).hexdigest()[:12]
        ENGINE_DIR.mkdir(parents=True, exist_ok=True)
        engine_path = ENGINE_DIR / f"ifnet_{tag}_{src_shape[2]}x{src_shape[3]}_{key}.engine"
        if not engine_path.exists():
            if not build:
                raise FileNotFoundError(f"no TensorRT engine built yet: {engine_path.name}")
            self._build(fast, src_shape, engine_path, device)
        runtime = trt.Runtime(self.logger)
        self.engine = runtime.deserialize_cuda_engine(engine_path.read_bytes())
        if self.engine is None:
            raise RuntimeError(f"could not load TensorRT engine {engine_path}")
        self.ctx = self.engine.create_execution_context()
        _, _, h, w = src_shape
        self.t = torch.full((1, 1, 1, 1), 0.5, dtype=torch.float32, device=device)
        self.out = torch.empty((1, 3, h, w), dtype=torch.float32, device=device)
        self.ctx.set_tensor_address("t", self.t.data_ptr())
        self.ctx.set_tensor_address("mid", self.out.data_ptr())

    def _build(self, fast: FastIFNet, src_shape: tuple, engine_path: Path, device: torch.device) -> None:
        trt = self.trt
        onnx_path = engine_path.with_suffix(".onnx")
        print(f"[trt] building {engine_path.name} (once, about a minute)...")
        t0 = time.perf_counter()
        src = torch.rand(src_shape, device=device)
        t = torch.full((1, 1, 1, 1), 0.5, device=device)
        with torch.no_grad():
            torch.onnx.export(_Export(fast), (src, src.clone(), t), str(onnx_path), dynamo=False, opset_version=17,
                              input_names=["src0", "src1", "t"], output_names=["mid"])
        builder = trt.Builder(self.logger)
        network = builder.create_network(1 << int(trt.NetworkDefinitionCreationFlag.STRONGLY_TYPED))
        parser = trt.OnnxParser(network, self.logger)
        # From memory rather than parse_from_file: TensorRT opens files by Windows' narrow (ANSI) names, so an
        # install folder with letters outside English (e.g. Chinese) failed here, during setup's Optimise step
        if not parser.parse(onnx_path.read_bytes()):
            errs = "; ".join(str(parser.get_error(i)) for i in range(parser.num_errors))
            raise RuntimeError(f"TensorRT could not parse the ONNX export: {errs}")
        config = builder.create_builder_config()
        config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, 2 << 30)
        config.builder_optimization_level = 4
        blob = builder.build_serialized_network(network, config)
        if blob is None:
            raise RuntimeError("TensorRT engine build failed")
        engine_path.write_bytes(bytes(blob))
        onnx_path.unlink(missing_ok=True)
        print(f"[trt] built in {time.perf_counter() - t0:.0f} s")

    def set_timestep(self, t: float) -> None:
        self.t.fill_(t)

    @torch.no_grad()
    def __call__(self, src0: torch.Tensor, src1: torch.Tensor) -> torch.Tensor:
        self.ctx.set_tensor_address("src0", src0.data_ptr())
        self.ctx.set_tensor_address("src1", src1.data_ptr())
        if not self.ctx.execute_async_v3(torch.cuda.current_stream().cuda_stream):
            raise RuntimeError("TensorRT execution failed")
        return self.out
