// NVIDIA VFG, an optional interpolation model (framegen/vfg.py): set up and removed on the Settings page, under
// "Interpolation model". It's NVIDIA's software under NVIDIA's licence, so nothing is downloaded until the user accepts
// that licence here; then python -m framegen.vfg_setup downloads NVIDIA's pinned package from NVIDIA's own index into
// runtime\vfx (Paths.Vfx, passed to every Python process as FRAMEGEN_VFX_PATH).
// Its output goes to logs\vfg-setup.txt (not *.log, so a diagnostics report still picks the last session's log).
// NVIDIA's licence also forbids publishing VFG's benchmark results, so nothing here shows or logs its speed. The same
// package brings RTX VSR (framegen/rtxvsr.py VfxVsr), under the same licence.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;

namespace SmoovPlay
{
    partial class Ui
    {
        Dictionary<string, object> vfgStatus;  // framegen.vfg_setup --status; null until it's read
        bool vfgLoading, vfgWorking, vfgCancelled, vfgThenDetect;
        bool detectAfterPlay;  // VFG was set up while playing: Auto-detect runs once play stops (OnPlayState)
        string vfgLine, vfgError;
        Process vfgProc;
        StackPanel vfgBox;  // under the Interpolation model row

        bool VfgInstalled { get { return vfgStatus != null && vfgStatus["installed"] is bool && (bool)vfgStatus["installed"]; } }
        string VfgUnsupported { get { return vfgStatus != null ? vfgStatus["unsupported"] as string ?? "" : ""; } }
        bool VfgReady { get { return VfgInstalled && VfgUnsupported.Length == 0; } }
        /// <summary>Why the NVIDIA VFG choice is greyed out when nothing is playing (null: it isn't).</summary>
        string VfgWhyNot
        {
            get
            {
                if (vfgStatus == null) return "Checking whether NVIDIA VFG is set up";
                if (VfgUnsupported.Length > 0) return VfgUnsupported;
                return VfgInstalled ? null : "Set it up first, below";
            }
        }

        void LoadVfgStatus()
        {
            if (vfgLoading || !paths.RuntimeReady) return;
            vfgLoading = true;
            Task.Run(() =>
            {
                Dictionary<string, object> st = null;
                try
                {
                    var lines = new List<string>();
                    int rc = Proc.Run(Proc.Python(paths.Python, "-m framegen.vfg_setup --status --json", paths.App), l => { lock (lines) lines.Add(l); }, null);
                    string json = lines.LastOrDefault(l => l.StartsWith("{"));
                    if (rc == 0 && json != null) st = Json.DeserializeObject(json) as Dictionary<string, object>;
                    else Program.Trace("vfg status: " + (lines.LastOrDefault(l => l.Trim().Length > 0) ?? "exit code " + rc));
                }
                catch (Exception e) { Program.Trace("vfg status: " + e.Message); }
                OnUi(() =>
                {
                    vfgLoading = false;
                    if (st != null) vfgStatus = st;
                    RefreshSettings();
                    BuildChips();
                    if (detectResult != null && !detecting) RenderDetect();  // Auto-detect's offer to set it up
                });
            });
        }

        /// <summary>The box under the Interpolation model row (BuildSettingRow adds it there).</summary>
        FrameworkElement VfgBox()
        {
            vfgBox = new StackPanel { Margin = new Thickness(0, 10, 0, 0) };
            AutomationProperties.SetAutomationId(vfgBox, "VfgBox");
            RenderVfg();
            return vfgBox;
        }

        void RenderVfg()
        {
            if (vfgBox == null) return;
            vfgBox.Children.Clear();
            Show(vfgBox, vfgStatus != null || vfgWorking);
            if (vfgStatus == null && !vfgWorking) return;
            string text, button = null, tip = null;
            Action click = null;
            bool enabled = true;
            if (vfgWorking)
            {
                text = vfgLine ?? "Starting";
                button = "Cancel";
                click = CancelVfg;
            }
            else if (VfgInstalled)
            {
                bool ours = vfgStatus["ours"] is bool && (bool)vfgStatus["ours"];
                text = VfgUnsupported.Length > 0 ? "NVIDIA VFG is set up, but this PC can't use it: " + VfgUnsupported
                     : "NVIDIA VFG is set up" + (ours ? "" : " (" + vfgStatus["path"] + ")") + ", and with it NVIDIA RTX VSR (Upscaler).";
                if (ours)
                {
                    button = "Remove";
                    click = AskRemoveVfg;
                    enabled = !SessionRunning;
                    tip = SessionRunning ? "Stop playing first: the video is using it." : "Deletes NVIDIA VFG's download (about " + vfgStatus["size_mb"] + " MB).";
                }
            }
            else if (VfgUnsupported.Length > 0)
                text = VfgUnsupported + " This PC can't use it, but RIFE 4.22 lite works on every graphics card SmoovPlay supports.";
            else
            {
                text = "NVIDIA VFG is optional: a separate download from NVIDIA (about " + vfgStatus["size_mb"] + " MB), under NVIDIA's licence. It also brings NVIDIA RTX VSR (Upscaler).";
                button = "Set up NVIDIA VFG";
                click = AskSetUpVfg;
            }

            var g = new Grid();
            g.ColumnDefinitions.Add(new ColumnDefinition());
            g.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            var t = new TextBlock { Style = S("Small"), Text = text, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 0, 12, 0) };
            AutomationProperties.SetAutomationId(t, "VfgText");
            g.Children.Add(t);
            if (button != null)
            {
                var b = new Button { Style = S(button == "Set up NVIDIA VFG" ? "Secondary" : "Ghost"), Content = button, IsEnabled = enabled, ToolTip = tip, VerticalAlignment = VerticalAlignment.Center };
                ToolTipService.SetShowOnDisabled(b, true);
                AutomationProperties.SetAutomationId(b, "Vfg" + button.Split(' ')[0]);
                b.Click += (s, e) => click();
                Grid.SetColumn(b, 1);
                g.Children.Add(b);
            }
            vfgBox.Children.Add(g);
            if (vfgError != null)
                vfgBox.Children.Add(new TextBlock { Style = S("Small"), Foreground = R("Bad"), Text = vfgError, Margin = new Thickness(0, 6, 0, 0) });
        }

        Dictionary<string, string> VfgLicences()
        {
            var d = new Dictionary<string, string>();
            foreach (Dictionary<string, object> l in (vfgStatus != null ? vfgStatus["licences"] as object[] : null) ?? new object[0])
                d[(string)l["name"]] = (string)l["url"];
            return d;
        }

        void AskSetUpVfg() { AskSetUpVfg(false); }

        /// <summary>thenDetect: asked from Auto-detect's offer (AutoDetect.cs), so Auto-detect runs again once it's set
        /// up, times it and suggests it if it keeps up.</summary>
        void AskSetUpVfg(bool thenDetect)
        {
            var licences = VfgLicences();
            Ask("\uE946", "Accent", "Set up NVIDIA VFG",
                "NVIDIA VFG is NVIDIA's software, not part of SmoovPlay. SmoovPlay downloads it from NVIDIA (about " + vfgStatus["size_mb"]
                + " MB), along with NVIDIA RTX VSR, and using them means you accept NVIDIA's licence: " + string.Join(", ", licences.Keys) + ". Among other things, it doesn't "
                + "allow publishing their speed or quality results, so SmoovPlay keeps them out of Copy diagnostics.",
                "Accept and download", "Read the licence", "Cancel", r =>
                {
                    if (r == 1) StartVfgInstall(thenDetect);
                    else if (r == 2)
                    {
                        foreach (var url in licences.Values) Proc.Open(url);
                        AskSetUpVfg(thenDetect);  // back to the question once they've read it
                    }
                });
        }

        void StartVfgInstall(bool thenDetect)
        {
            if (vfgWorking) return;
            vfgWorking = true;
            vfgThenDetect = thenDetect;
            vfgCancelled = false;
            vfgError = null;
            vfgLine = "Starting the download";
            RenderVfg();
            if (detectResult != null) RenderDetect();  // its offer's button: "Setting up..."
            string log = Path.Combine(paths.Logs, "vfg-setup.txt");
            string tmp = Path.Combine(paths.Runtime, "tmp-vfx");  // pip's download goes on the install drive, not C:\...\Temp
            Task.Run(() =>
            {
                int rc = -1;
                string last = null;
                var progress = new Regex(@"^Progress (\d+) of (\d+)");
                try
                {
                    Directory.CreateDirectory(paths.Logs);
                    Directory.CreateDirectory(tmp);
                    using (var w = new StreamWriter(log, false))
                    {
                        string args = "-m framegen.vfg_setup --install --accept-nvidia-licence --target \"" + paths.Vfx + "\""
                                      + (SystemCheck.Proxy != null ? " --proxy \"" + SystemCheck.Proxy + "\"" : "");
                        var psi = Proc.Python(paths.Python, args, paths.App);
                        psi.EnvironmentVariables["TMP"] = tmp;
                        psi.EnvironmentVariables["TEMP"] = tmp;
                        rc = Proc.Run(psi, line =>
                        {
                            var m = progress.Match(line);
                            if (m.Success)
                            {
                                double c = double.Parse(m.Groups[1].Value), t = double.Parse(m.Groups[2].Value);
                                string text = $"Downloading NVIDIA VFG: {c / 1e6:0} of {t / 1e6:0} MB";
                                OnUi(() => { if (vfgWorking && !vfgCancelled) { vfgLine = text; RenderVfg(); } });
                                return;
                            }
                            lock (w) w.WriteLine(line);
                            if (line.Trim().Length > 0) last = line;
                            if (line.StartsWith("Installing collected packages") || line.StartsWith("Successfully installed"))
                                OnUi(() => { if (vfgWorking && !vfgCancelled) { vfgLine = "Installing NVIDIA VFG"; RenderVfg(); } });
                        }, pr => vfgProc = pr);
                    }
                }
                catch (Exception e) { last = e.Message; }
                finally
                {
                    vfgProc = null;
                    try { Directory.Delete(tmp, true); } catch (Exception) { }
                }
                OnUi(() =>
                {
                    vfgWorking = false;
                    if (vfgCancelled) vfgError = null;
                    else if (rc == 0)
                    {
                        // Offered, not switched to: RIFE stays picked until they choose VFG (or apply Auto-detect's
                        // suggestion). Not while playing: the running session started without VFG.
                        // Auto-detect again, which times it: asked for by its offer, or its results on the page are
                        // out of date now (they say "Not set up"). While playing, once play stops (OnPlayState).
                        bool redetect = vfgThenDetect || detectResult != null;
                        if (redetect && !SessionRunning && !detecting)
                        {
                            Toast("NVIDIA VFG is set up. Auto-detect is timing it now", false);
                            RunDetect();
                        }
                        else if (redetect && SessionRunning)
                        {
                            detectAfterPlay = true;
                            Toast("NVIDIA VFG is set up. Auto-detect times it once you stop playing", false);
                        }
                        else if (SettingText("model") == "vfg") Toast("NVIDIA VFG is set up", false);
                        else if (SessionRunning) Toast("NVIDIA VFG is set up. Pick it under Interpolation model once you stop playing", false);
                        else Toast("NVIDIA VFG is set up. RIFE 4.22 lite stays picked until you switch", false, "Use it now", UseVfgNow);
                    }
                    else
                    {
                        string why = last != null && last.StartsWith("[vfg] ") ? last.Substring(6) : last;
                        vfgError = "Setting up NVIDIA VFG didn't work: " + Shorten(why ?? "exit code " + rc, 200) + ". Its log is " + log + ".";
                        Program.Trace("vfg setup: " + vfgError);
                    }
                    vfgStatus = null;  // read again: the box shows "set up" from the real state, not from the exit code
                    LoadVfgStatus();
                    RenderVfg();
                    if (page == "PageSettings") SnapLater("vfg-setup", 500);
                });
            });
        }

        void CancelVfg()
        {
            var pr = vfgProc;
            if (!vfgWorking || pr == null) return;
            vfgCancelled = true;
            vfgLine = "Stopping";
            RenderVfg();
            // pip runs as a child of the setup script, so the whole tree goes (the next attempt clears what's left).
            try { Process.Start(new ProcessStartInfo("taskkill", "/T /F /PID " + pr.Id) { CreateNoWindow = true, UseShellExecute = false }); }
            catch (Exception) { try { pr.Kill(); } catch (Exception) { } }
        }

        /// <summary>The setup toast's "Use it now": picks NVIDIA VFG as the interpolation model.</summary>
        void UseVfgNow()
        {
            if (SessionRunning) { Toast("Stop playing first, then pick NVIDIA VFG under Interpolation model", true); return; }
            try { WriteSetting("model", "vfg"); }
            catch (Exception e) { Toast("Couldn't save the setting: " + e.Message, true); return; }
            RefreshSettings();
            BuildChips();
            Toast("NVIDIA VFG picked. RIFE 4.22 lite is still there, under Interpolation model", false);
        }

        void AskRemoveVfg()
        {
            if (SessionRunning) { Toast("Stop playing first: the video is using NVIDIA VFG", true); return; }
            Ask("\uE74D", "Warn", "Remove NVIDIA VFG?",
                "This deletes NVIDIA VFG's download (about " + vfgStatus["size_mb"] + " MB) and switches back to RIFE 4.22 lite. You can set it up again any time.",
                "Remove", null, "Cancel", r =>
                {
                    if (r != 1) return;
                    vfgWorking = true;
                    vfgLine = "Removing NVIDIA VFG";
                    vfgError = null;
                    RenderVfg();
                    Task.Run(() =>
                    {
                        var lines = new List<string>();
                        int rc;
                        try { rc = Proc.Run(Proc.Python(paths.Python, "-m framegen.vfg_setup --remove --target \"" + paths.Vfx + "\"", paths.App), l => { lock (lines) lines.Add(l); }, null); }
                        catch (Exception e) { lines.Add(e.Message); rc = -1; }
                        OnUi(() =>
                        {
                            vfgWorking = false;
                            if (rc == 0)
                            {
                                var spec = settingSpecs != null ? settingSpecs.FirstOrDefault(s => s.Key == "model") : null;
                                if (SettingText("model") == "vfg" && spec != null) { try { WriteSetting("model", spec.Default); } catch (Exception) { } }
                                Toast("NVIDIA VFG removed", false);
                            }
                            else
                            {
                                string last = lines.LastOrDefault(l => l.Trim().Length > 0) ?? "exit code " + rc;
                                vfgError = "Couldn't remove NVIDIA VFG: " + Shorten(last.StartsWith("[vfg] ") ? last.Substring(6) : last, 200);
                            }
                            vfgStatus = null;
                            LoadVfgStatus();
                            RenderVfg();
                        });
                    });
                });
        }
    }
}
