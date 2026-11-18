# Changelog

## 0.3.1

**Play**
- **Game frame rate: 30 fps** (Settings, Smoothness; and the in-video menu). For a game locked at 30 fps: every
  other frame is taken as new, so motion stays even whatever the scene. With PS5 Remote Play, frames are counted by
  the stream's own numbers, so frames lost on the way don't throw the rhythm off. On Auto, a still or dark scene could make
  SmoovPlay read a locked-30 game (Gotham Knights on PS5) as 40 fps or more, which made motion uneven and kept
  turning Even out 40-60 fps on and off. Simulate a 30 fps game was the way round it, but that's a test mode: it also
  scores every frame, which costs graphics card time at 90 fps. The new setting is saved, as everything else you
  change in the in-video menu is.
- **A frame log for each PS5 Remote Play session**, next to its log (frames-*.csv, the last 10 kept, about 1.5 MB per
  5 minutes, no pictures): each frame's size and timing and what SmoovPlay made of it, so Auto can be tuned on real
  games.

**Fixes**
- **Alt+Tab works while the video is fullscreen.** Fullscreen was an always-on-top window, so switching to another
  program left the video over it. It's now a borderless window over the monitor, as games' borderless mode.
- **The video window's keys work without a click again** when it opens behind chiaki-ng or the launcher. It took the
  keys only if nothing had been pressed or moved since it opened (moving the mouse counted), and only after
  chiaki-ng was minimised, which can leave no window to take them from. It now takes them as it opens, before
  minimising chiaki-ng, and the log says if it had to try again.
- **Esc no longer freezes the video window while a before & after video is being made.** The window closes straight
  away and the video carries on in the background; the launcher says when it's saved, with a button to show it.
  Update, Repair and Uninstall ask first while one is being made.
- **Stop in the launcher ends a session gracefully**, the same as Esc (a second Stop, or 20 s, forces it).
- **Results no longer say "about 60 fps, between 30 and 60"** when a game ran unevenly: they say how long it ran
  between 30 and 60 fps and that its frames were evened out.
- **chiaki-ng stays minimised after Alt+Tab.** It was only minimised in the stream's first seconds, so after
  switching to its window and back, its unsmoothed picture stayed up beside SmoovPlay's. Thanks to
  [@Vadko](https://github.com/Vadko) ([#5](https://github.com/smoovplay/smoovplay/pull/5))!
- **The PC check recognises 6 GHz Wi-Fi** (Windows 11), which it used to call 2.4 or 5 GHz. Thanks to
  [@Vadko](https://github.com/Vadko) ([#4](https://github.com/smoovplay/smoovplay/pull/4))!

**Capture cards** (Experimental)
- **Finding cards is sturdier** ([#2](https://github.com/smoovplay/smoovplay/issues/2), an Elgato HD60 X that
  wasn't listed):
  - SmoovPlay now reads device names from Windows' list without loading each camera's driver, as OBS does. Before,
    it opened every camera and virtual camera to see what it carried, so one faulty driver could stop the whole
    list (or Play) before the card was found. Only the card you pick is opened.
  - Cards that report video and sound together were dropped from the list without a word; they're listed now.
  - An empty list is looked at once more half a second later, and looking gives up after 30 s instead of waiting
    forever on a driver that doesn't answer.
  - The Play page says which it is: the list failed (and why), Windows has sound devices only, or there's no card.
- **When a card won't open, it says why**: in use by another app (many cards, Elgato's USB ones among them, work
  with one app at a time: close OBS or Elgato's apps first), blocked by Windows' camera privacy setting, or
  unplugged.
- **The log notes a card on a USB 2 port** (1280×720 at 30 fps at most) and a card offering 10-bit HDR, which
  SmoovPlay can't read yet: it uses 8-bit, so turn HDR off on the console if the picture looks washed out.

**App window** (Experimental)
- **The Xbox app is found again** ([#1](https://github.com/smoovplay/smoovplay/issues/1),
  [#3](https://github.com/smoovplay/smoovplay/issues/3)). Its current version runs as XboxPcAppCE.exe, which
  SmoovPlay didn't know, and Microsoft Store apps draw inside a frame window that SmoovPlay skipped. Both are listed
  now, under the app's own name.
- **When a streaming app is running but can't be picked** (in the tray, on another desktop, too small), the Play
  page says so and what to do.
- **The smooth picture fits the app's window.** It was drawn at 16:9 inside it, so a window of another shape (a
  browser's, say) looked squeezed, with bars over part of the app. It now lines up with the app exactly, even when
  the window hangs off the screen.
- **SmoovPlay's keys work while the app has the keyboard**: Ctrl+Alt with the usual key, from anywhere. Ctrl+Alt+M
  menu (then the arrows, Enter and Esc work in it until it closes), Ctrl+Alt+F fullscreen, Ctrl+Alt+Esc quit,
  Ctrl+Alt+S stats, Ctrl+Alt+I smooth on/off. Before, M, F and Esc went to the app, and only Stop in the launcher
  ended it. The video lists them when it starts and when the mouse moves over it, and the Play page has them in a
  card with **Change keys**: click one and press new keys. A key another program already has is skipped for the
  next one (Ctrl+Alt+Space for the menu, Ctrl+Alt+End to quit), and the Play page says so.

**Launcher**
- **Check for updates** under the version number on the left. The automatic check now runs every 6 hours, not 20.
- **Copy diagnostics** (and Send feedback) say more and share less:
  - the source you play from, its own PC check, and for capture cards the devices Windows lists, the card's driver
    state and USB IDs, and why a device list failed; for App window, the streaming apps found and a count of other
    windows (never their titles)
  - your Windows user name is left out of every path, whatever its capitals (some were missed before), and device
    names like "Alex's iPhone" lose the name
  - Windows 11 is called Windows 11 (Windows itself still says "Windows 10" in the place SmoovPlay read)
- **Frame tap is labelled "for developers"**, and points app users to App window: it only works with an app built
  to send frames to SmoovPlay.

## 0.3.0

**Play**
- **A minimal stats overlay**, now the default: a small line in the corner with the frames on screen, the game's own
  frame rate (amber when it isn't 30 fps) and the delay, and a dot: green, your PC keeps up; amber, it's tight; red,
  it's falling behind. Settings → Display → Stats overlay style has Detailed for everything as before; **S** goes
  Off, Minimal, Detailed.
- **Keys work in the video window straight away.** It no longer needs a click before M, F or Esc do anything, and
  chiaki-ng stays minimised when it shows its window again just after the stream starts. The video window shows its
  keys when it opens (M menu, F fullscreen, Esc quit), and again when you move the mouse over it.
- **The in-video menu stays still** while you go up and down it: the space for each setting's description is
  the same size whichever one is picked, so the rows no longer jump.
- **Test results say quality in plain terms**: the share of each frame that's visibly off from the real one (lower is
  better), instead of dB. It's only given when there's enough to go on: at 90 fps, or with a game that isn't at a
  steady 60, a few seconds of fair frames.
- **Instant replay at 120 fps keeps 60 fps clips** (every other frame). Encoding all 120 a second fell behind,
  dropping frames from clips, and took graphics card time from play.

**For developers** (Experimental)
- **The frame tap is documented for any app** ([docs/frame-tap.md](docs/frame-tap.md)): the shared memory
  chiaki-ng sends PS5 Remote Play's frames through. An app can now send decoded frames too (NV12 or BGRA), and
  say which are repeats, or send pictures only when they change. Pick **Frame tap** on the Play page (or
  `run.py --source tap`). `scripts/frametap_send.py` and `docs/frame-tap-writer.c` are writers to start from.
  Tested with those, not yet with another app.
- **A slimmer chiaki-ng patch**: the tap's code now lives in its own files (`chiaki_tap/frametap_session.cpp`), and
  chiaki-ng's own files only get one-line calls, so a new chiaki-ng version is quicker to patch.

## 0.2.0

**Experimental** (please send feedback)
- **HDR** (Settings → Picture → HDR, off by default). For a PS5 streaming in HDR, pick chiaki-ng's H.265 HDR codec
  and turn this on. **On, shown in SDR** gives the stream its real colours on any monitor, where before it looked
  washed out, for about 0.7 ms of graphics card time a frame. **On, HDR output** keeps the picture HDR10 all the way
  to a monitor with Windows' HDR on; Looks and RTX VSR are off with it, and instant replay clips are saved in SDR.
  Tried with a stand-in for a PS5's HDR stream, not a real one yet; HDR output was checked by reading back the
  10-bit picture it sends, not on an HDR screen.

**Play**
- An HDR stream with HDR off now says how to fix the washed-out colours.

**Launcher**
- The PS5 guide explains the HDR codec instead of saying to turn HDR off. HDR has the Experimental badge and a
  Send feedback button on the Settings page.

**Fixes**
- **Low delay** presentation could hand Windows a black buffer instead of the new frame on some refreshes (found by
  reading back what it sent). Each frame is now copied into place, for one quick graphics card copy.

## 0.1.0 (early release)

The first public version. Windows 10 or 11, with an NVIDIA RTX graphics card recommended.

**Play**
- Plays your PS5 on the PC over Remote Play, through chiaki-ng (the open-source Remote Play app, with SmoovPlay's
  frame tap built in). Nothing is installed on the console.
- A 30 fps game becomes 60, 90 or 120 fps: RIFE 4.22 lite draws the in-between frames (TensorRT or PyTorch on the
  graphics card), and repeats and scene cuts are found so they aren't blended.
- AMD FSR 1 scales the 1080p stream to your monitor (RTX VSR too, when running from source).
- **Sound in sync:** chiaki-ng holds the game's sound back to meet the picture.
- **Delay test:** press L while playing; SmoovPlay presses a button through chiaki-ng and times how long the PS5
  takes to show it.
- **Test mode:** try it with a 60 fps game, played as a 30 fps one, with every AI frame scored against the real one.
- When no picture arrives, the video window says why, for example that chiaki-ng isn't streaming yet.
- **Instant replay:** keep the last 30 seconds to 5 minutes and press R (or Ctrl+Alt+R anywhere) to save it as an
  MP4 at the frame rate you see, with the game's own sound from PS5 Remote Play or a capture card. B saves a before
  & after video: the game's own frames next to SmoovPlay's, split screen or side by side. Recorded on the graphics
  card's video encoder; off until you pick a length.
- **Looks:** stack effects like the nodes of a color grading app (color, color wheels, split tone, LUTs, bloom,
  halation, blur, clarity, chromatic aberration, sharpening, film grain, vignette, scanlines, letterbox, color-blind
  assist) and see the result live on the game while you edit. 14 looks to start from. K turns the look on and off
  and J goes to the next one. Share a look as a short code that anyone can paste. Clips stay clean unless you turn
  on Looks in clips.
- Optional NVIDIA Video Frame Generation (VFG) as the interpolation model on RTX 40 and 50 series cards: set up from
  the launcher, downloaded from NVIDIA under its licence, not part of SmoovPlay.

**Launcher**
- One installer: checks the PC, downloads the AI runtime from official sources, and walks you through pairing the
  PS5. Installs for your Windows user only, without admin rights.
- Settings with quick picks, and the rough picture and speed impact of each choice.
- **Updates itself:** when a new version is out, one click downloads it, checks its signature and installs it,
  keeping your settings, looks and clips.
- A Looks page to make, change and share looks, drawn as you edit on sample screenshots from GTA VI and five other
  games, and shown live on the video while you play.
- Opens where it was last left.

**Experimental** (built and tested with stand-ins, not yet on real hardware: please send feedback)
- **AMD Radeon and Intel Arc cards:** RIFE through DirectML. The same frames as the NVIDIA engine; on the
  development PC's NVIDIA card it took about 1.7 times as long as TensorRT. Not yet tried on an AMD or Intel card.
- **Even out 40-60 fps:** games whose frame rate wanders between 40 and 60 have each frame timed and evenly spaced
  frames drawn from them, instead of some staying on screen twice as long. Tried with real footage played as 43
  and 47 fps games, not yet with a real one.
- **Capture cards:** any console with HDMI, through a capture card, with its sound held back to meet the picture.
  MJPEG cards are decoded on the graphics card. On a PS5, turn off HDCP while you use one.
- **App window:** the window of the app you stream with (the Xbox app, Sony's PS Remote Play app, Moonlight, a
  browser playing a cloud game), captured on the graphics card and shown smoothly over it. The repeat check learns
  the stream's look and keeps to a 30 fps game's rhythm.
- **Low delay** window presentation (a DXGI flip-model swap chain).

**Known limits**
- The installer isn't code-signed yet: Windows shows "Windows protected your PC" (More info, then Run anyway). The
  README explains why, and how to check the file is the real one.
- Tested on one PC so far, with an RTX 4070 Ti SUPER. Other RTX 30, 40 and 50 series cards should work; RTX 20
  cards and laptops aren't tested yet.
- If the picture stays black, or the PS5 says the content can't be shown, turn off HDCP on the PS5 (Settings →
  System → HDMI) and turn it back on when you're done.
- With an app window, the app's sound comes a little ahead of the smooth picture.
- See the README's Known limits for the rest.
