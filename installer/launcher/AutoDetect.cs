// Auto-detect, at the top of the Settings page: runs python -m framegen.autodetect (a ~10 s test of the graphics card,
// the display and what's installed; see framegen/autodetect.py) and shows what it found and what it suggests, with the
// reason for each. Apply changes the settings the same way picking them on the page does. The test needs the graphics
// card to itself, so it can't run while playing, and Play waits for it.
// Its output goes to logs\autodetect.txt (not *.log, so a diagnostics report still picks the last session's log).

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Animation;

namespace SmoovPlay
{
    partial class Ui
    {
        const string DetectPrefix = "[detect-result] ", DetectLine = "[detect] ";
        bool detecting, detectApplied;
        readonly HashSet<string> detectChanged = new HashSet<string>();  // what Apply changed, to mark them afterwards
        string detectProgress, detectError;
        Dictionary<string, object> detectResult;
        Button detectApply;

        void RunDetect()
        {
            if (detecting || !paths.RuntimeReady) return;
            if (SessionRunning) { Toast("Stop playing first: the test needs the graphics card to itself", true); return; }
            detecting = true;
            detectResult = null;
            detectError = null;
            detectApplied = false;
            detectProgress = "Starting the test";
            RenderDetect();
            string log = Path.Combine(paths.Logs, "autodetect.txt");
            Task.Run(() =>
            {
                string json = null, last = null;
                int rc = -1;
                try
                {
                    Directory.CreateDirectory(paths.Logs);
                    using (var w = new StreamWriter(log, false))
                    {
                        string args = "-m framegen.autodetect --settings \"" + Paths.SettingsFile + "\" "
                                      + Environment.GetEnvironmentVariable("SMOOVPLAY_DETECT_ARGS");  // testing: --timing FULL,HALF
                        rc = Proc.Run(Proc.Python(paths.Python, args, paths.App), line =>
                        {
                            lock (w) w.WriteLine(line);
                            if (line.StartsWith(DetectPrefix)) { json = line.Substring(DetectPrefix.Length); return; }
                            if (line.Trim().Length > 0) last = line;
                            if (line.StartsWith(DetectLine) && !line.Contains("ERROR"))
                            {
                                string step = line.Substring(DetectLine.Length);
                                OnUi(() => { if (!detecting) return; detectProgress = char.ToUpper(step[0]) + step.Substring(1); RenderDetect(); });
                            }
                        }, null);
                    }
                }
                catch (Exception e) { last = e.Message; }
                OnUi(() =>
                {
                    detecting = false;
                    try { if (json != null) detectResult = Json.DeserializeObject(json) as Dictionary<string, object>; }
                    catch (Exception e) { last = e.Message; }
                    if (detectResult == null)
                    {
                        string why = last != null && last.StartsWith(DetectLine) ? last.Substring(DetectLine.Length).Replace("ERROR: ", "") : last;
                        detectError = rc == 2 ? "PyTorch can't use an NVIDIA graphics card here. Update the NVIDIA driver (see the PC check), then try again."
                            : "The test didn't finish: " + Shorten(why ?? "exit code " + rc, 180) + ". Its log is " + log + ".";
                        Program.Trace("auto-detect: " + detectError);
                    }
                    RenderDetect();
                    if (page == "PageSettings") SnapLater("autodetect", 500);
                });
            });
        }

        /// <summary>A setting's value as the page shows it now: the running session's, else the file's, else the default.</summary>
        object CurrentSetting(SettingSpec spec)
        {
            var values = liveState != null ? liveState["values"] as Dictionary<string, object> : null;
            if (values != null && values.ContainsKey(spec.Key)) return values[spec.Key];
            var file = ReadSettingsFile();
            if (file.ContainsKey(spec.Key) && spec.Choices.Any(c => Same(c.Key, file[spec.Key]))) return file[spec.Key];
            return spec.Default;
        }

        string ChoiceName(SettingSpec spec, object value)
        {
            var c = spec.Choices.FirstOrDefault(x => Same(x.Key, value));
            return c.Value ?? Json.Serialize(value).Trim('"');
        }

        /// <summary>The suggestions that differ from the current settings, in the page's order.</summary>
        List<KeyValuePair<SettingSpec, object>> DetectChanges()
        {
            var list = new List<KeyValuePair<SettingSpec, object>>();
            var suggested = detectResult != null ? detectResult["settings"] as Dictionary<string, object> : null;
            if (suggested == null || settingSpecs == null) return list;
            foreach (var spec in settingSpecs)
                if (suggested.ContainsKey(spec.Key) && !Same(CurrentSetting(spec), suggested[spec.Key]))
                    list.Add(new KeyValuePair<SettingSpec, object>(spec, spec.Choices.First(c => Same(c.Key, suggested[spec.Key])).Key));
            return list;
        }

        void ApplyDetect()
        {
            var changes = DetectChanges();
            detectChanged.Clear();
            foreach (var c in changes) { ChangeSetting(c.Key, c.Value); detectChanged.Add(c.Key.Key); }
            detectApplied = true;
            RenderDetect();
            if (page == "PageSettings") SnapLater("autodetect-applied", 500);
            Toast(changes.Count == 1 ? "1 setting changed" : changes.Count + " settings changed", false);
        }

        void DismissDetect()
        {
            detectResult = null;
            detectError = null;
            detectApplied = false;
            RenderDetect();
        }

        /// <summary>The button: off while playing (the test would slow the video and measure wrong) or testing.</summary>
        void UpdateDetect()
        {
            var b = B("BtnDetect");
            bool can = paths.RuntimeReady && settingSpecs != null && !SessionRunning && !detecting;
            b.IsEnabled = can;
            b.Content = detecting ? "Testing..." : detectResult != null || detectError != null ? "Run again" : "Auto-detect";
            b.ToolTip = SessionRunning ? "Stop playing first: the test needs the graphics card to itself."
                : !paths.RuntimeReady ? "Finish setting up SmoovPlay first." : null;
            if (detectApply != null) detectApply.IsEnabled = !(SessionRunning && liveState == null);  // starting: settings are locked
        }

        void RenderDetect()
        {
            var body = E<StackPanel>("DetectBody");
            body.Children.Clear();
            detectApply = null;
            if (detecting) body.Children.Add(DetectRunning());
            else if (detectError != null)
                body.Children.Add(new TextBlock { Style = S("Small"), Foreground = R("Bad"), Text = detectError });
            else if (detectResult != null) DetectResults(body);
            Show(body, body.Children.Count > 0);
            UpdateDetect();
        }

        FrameworkElement DetectRunning()
        {
            var sp = new StackPanel();
            var track = new Border { Height = 3, Width = 260, CornerRadius = new CornerRadius(1.5), Background = R("Line2"), HorizontalAlignment = HorizontalAlignment.Left, ClipToBounds = true };
            var move = new TranslateTransform();
            track.Child = new Border { Width = 80, CornerRadius = new CornerRadius(1.5), Background = R("Accent"), HorizontalAlignment = HorizontalAlignment.Left, RenderTransform = move };
            move.BeginAnimation(TranslateTransform.XProperty, new DoubleAnimation(-80, 260, TimeSpan.FromSeconds(1.4)) { RepeatBehavior = RepeatBehavior.Forever });
            sp.Children.Add(track);
            var t = new TextBlock { Style = S("Small"), Text = detectProgress + "...", Margin = new Thickness(0, 9, 0, 0) };
            AutomationProperties.SetAutomationId(t, "DetectProgress");
            sp.Children.Add(t);
            return sp;
        }

        void DetectResults(StackPanel body)
        {
            body.Children.Add(Overline("FOUND ON THIS PC", 0));
            var found = new Grid();
            found.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(118) });
            found.ColumnDefinitions.Add(new ColumnDefinition());
            foreach (Dictionary<string, object> f in (detectResult["found"] as object[]) ?? new object[0])
            {
                found.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
                int r = found.RowDefinitions.Count - 1;
                var label = new TextBlock { Text = (string)f["label"], FontSize = 12.5, Foreground = R("Muted"), Margin = new Thickness(0, 0, 0, 5) };
                var value = new TextBlock { FontSize = 12.5, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 0, 0, 5) };
                value.Inlines.Add(new System.Windows.Documents.Run((string)f["value"]));
                string detail = f["detail"] as string;
                if (!string.IsNullOrEmpty(detail)) value.Inlines.Add(new System.Windows.Documents.Run("  ·  " + detail) { Foreground = R("Text2") });
                Grid.SetRow(label, r); Grid.SetRow(value, r); Grid.SetColumn(value, 1);
                found.Children.Add(label);
                found.Children.Add(value);
            }
            body.Children.Add(found);

            var suggested = detectResult["settings"] as Dictionary<string, object> ?? new Dictionary<string, object>();
            var reasons = detectResult["reasons"] as Dictionary<string, object> ?? new Dictionary<string, object>();
            var changes = DetectChanges();
            body.Children.Add(Overline(detectApplied ? "APPLIED" : "SUGGESTED", 14));
            foreach (var spec in (settingSpecs ?? new List<SettingSpec>()).Where(s => suggested.ContainsKey(s.Key)))
            {
                var change = changes.FirstOrDefault(c => c.Key == spec);
                var row = new Grid { Margin = new Thickness(0, 0, 0, 10) };
                row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(150) });
                row.ColumnDefinitions.Add(new ColumnDefinition());
                row.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
                row.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
                row.Children.Add(new TextBlock { Text = spec.Label, FontSize = 13, FontWeight = FontWeights.SemiBold });
                var value = new TextBlock { FontSize = 13 };
                if (change.Key != null)
                {
                    value.Inlines.Add(new System.Windows.Documents.Run(ChoiceName(spec, CurrentSetting(spec))) { Foreground = R("Muted"), TextDecorations = TextDecorations.Strikethrough });
                    value.Inlines.Add(new System.Windows.Documents.Run("  →  ") { Foreground = R("Muted") });
                    value.Inlines.Add(new System.Windows.Documents.Run(ChoiceName(spec, change.Value)) { Foreground = R("Accent"), FontWeight = FontWeights.SemiBold });
                }
                else
                {
                    value.Inlines.Add(new System.Windows.Documents.Run(ChoiceName(spec, suggested[spec.Key])));
                    bool changed = detectApplied && detectChanged.Contains(spec.Key);
                    value.Inlines.Add(new System.Windows.Documents.Run(changed ? "   changed" : "   already set") { Foreground = R(changed ? "Good" : "Muted"), FontSize = 12 });
                }
                AutomationProperties.SetAutomationId(value, "Detect_" + spec.Key);
                Grid.SetColumn(value, 1);
                row.Children.Add(value);
                if (reasons.ContainsKey(spec.Key))
                {
                    var why = new TextBlock { Style = S("Small"), Text = (string)reasons[spec.Key], Margin = new Thickness(0, 3, 0, 0) };
                    Grid.SetRow(why, 1); Grid.SetColumnSpan(why, 2);
                    row.Children.Add(why);
                }
                body.Children.Add(row);
            }

            foreach (string note in (detectResult["notes"] as object[]) ?? new object[0])
            {
                var g = new Grid { Margin = new Thickness(0, 2, 0, 8) };
                g.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
                g.ColumnDefinitions.Add(new ColumnDefinition());
                g.Children.Add(new TextBlock { Style = S("Icon"), Text = "", FontSize = 13, Foreground = R("Warn"), VerticalAlignment = VerticalAlignment.Top, Margin = new Thickness(0, 2, 9, 0) });
                var t = new TextBlock { Style = S("Small"), Foreground = R("Text"), Text = note };
                Grid.SetColumn(t, 1);
                g.Children.Add(t);
                body.Children.Add(g);
            }

            string offer = detectResult.ContainsKey("vfg_offer") ? detectResult["vfg_offer"] as string : null;
            if (!string.IsNullOrEmpty(offer) && !VfgInstalled)
                body.Children.Add(VfgOffer(offer));

            var buttons = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 8, 0, 0) };
            if (detectApplied)
            {
                buttons.Children.Add(new TextBlock { Style = S("Icon"), Text = "", FontSize = 13, Foreground = R("Good"), Margin = new Thickness(0, 0, 8, 0) });
                buttons.Children.Add(new TextBlock { Style = S("Small"), Foreground = R("Text"), VerticalAlignment = VerticalAlignment.Center, Text = "Done. Fine-tune anything below; Auto-detect won't change it again unless you run it." });
                buttons.Children.Add(DetectButton("BtnDetectDismiss", "Ghost", "Hide", DismissDetect, new Thickness(12, 0, 0, 0)));
            }
            else if (changes.Count == 0)
            {
                buttons.Children.Add(new TextBlock { Style = S("Small"), Foreground = R("Text"), VerticalAlignment = VerticalAlignment.Center, Text = "Your settings already match this PC." });
                buttons.Children.Add(DetectButton("BtnDetectDismiss", "Ghost", "Hide", DismissDetect, new Thickness(12, 0, 0, 0)));
            }
            else
            {
                detectApply = DetectButton("BtnDetectApply", "Primary", changes.Count == 1 ? "Apply this change" : "Apply " + changes.Count + " changes", ApplyDetect, new Thickness(0));
                buttons.Children.Add(detectApply);
                buttons.Children.Add(DetectButton("BtnDetectDismiss", "Ghost", "Not now", DismissDetect, new Thickness(8, 0, 0, 0)));
            }
            body.Children.Add(buttons);
        }

        /// <summary>Auto-detect's offer to set up NVIDIA VFG (framegen/autodetect.py vfg_offer: an RTX 40 or 50 series card
        /// without it), with a button for it. Setting it up from here runs Auto-detect again (Vfg.cs), which then times
        /// VFG and suggests it if it keeps up.</summary>
        FrameworkElement VfgOffer(string text)
        {
            var g = new Grid { Margin = new Thickness(0, 4, 0, 8) };
            g.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            g.ColumnDefinitions.Add(new ColumnDefinition());
            g.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            g.Children.Add(new TextBlock { Style = S("Icon"), Text = "", FontSize = 13, Foreground = R("Accent"), VerticalAlignment = VerticalAlignment.Top, Margin = new Thickness(0, 2, 9, 0) });
            var t = new TextBlock { Style = S("Small"), Foreground = R("Text"), Text = text, VerticalAlignment = VerticalAlignment.Center };
            AutomationProperties.SetAutomationId(t, "DetectVfgOffer");
            Grid.SetColumn(t, 1);
            g.Children.Add(t);
            var b = DetectButton("BtnDetectVfg", "Secondary", vfgWorking ? "Setting up..." : "Set up NVIDIA VFG", () => AskSetUpVfg(true), new Thickness(12, 0, 0, 0));
            b.VerticalAlignment = VerticalAlignment.Center;
            b.IsEnabled = vfgStatus != null && !vfgWorking;
            if (vfgStatus == null) b.ToolTip = "Checking whether NVIDIA VFG is set up";
            ToolTipService.SetShowOnDisabled(b, true);
            Grid.SetColumn(b, 2);
            g.Children.Add(b);
            return g;
        }

        TextBlock Overline(string text, double top)
        {
            return new TextBlock { Text = text, FontSize = 11, FontWeight = FontWeights.SemiBold, Foreground = R("Muted"), Margin = new Thickness(0, top, 0, 8) };
        }

        Button DetectButton(string id, string style, string text, Action click, Thickness margin)
        {
            var b = new Button { Style = S(style), Content = text, Height = 34, Padding = new Thickness(14, 0, 14, 0), Margin = margin };
            AutomationProperties.SetAutomationId(b, id);
            b.Click += (s, e) => click();
            return b;
        }
    }
}
