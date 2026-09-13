// Development-only source build: real public scenes, no runtime substitutions.
using System;
using System.IO;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

public static class CpswmBuild {
    // Hub owns the authenticated launch. Do not copy its session credentials into a script.
    [MenuItem("CPSWM/Build Frozen Mac Development")]
    public static void MacDevelopmentFromHub() {
        string project = Directory.GetParent(Application.dataPath).FullName;
        string revision;
        var start = new System.Diagnostics.ProcessStartInfo("/usr/bin/git", "rev-parse HEAD") {
            WorkingDirectory = project,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true
        };
        using (var process = System.Diagnostics.Process.Start(start)) {
            revision = process.StandardOutput.ReadToEnd().Trim();
            if (!process.WaitForExit(10000) || process.ExitCode != 0
                || !System.Text.RegularExpressions.Regex.IsMatch(revision, "\\A[0-9a-f]{40}\\z")) {
                throw new InvalidOperationException("Cannot bind the local source revision.");
            }
        }
        string directory = Path.Combine(Path.GetTempPath(), "cpswm-unity-gui-build-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        Debug.Log("CPSWM_BUILD_OUTPUT " + directory);
        BuildAt(Path.Combine(directory, "cpswm-development.app"),
            Path.Combine(directory, "unity-result.json"), revision);
    }

    [Serializable]
    private class Receipt {
        public string schema = "cpswm-unity-build@1";
        public string editorVersion;
        public string result;
        public string outputPath;
        public string sourceRevision;
        public int errors;
        public int warnings;
        public bool humanExecutionVerified = false;
    }

    public static void MacDevelopment() {
        string destination = Environment.GetEnvironmentVariable("CPSWM_UNITY_OUTPUT");
        string receiptPath = Environment.GetEnvironmentVariable("CPSWM_UNITY_RECEIPT");
        string sourceRevision = Environment.GetEnvironmentVariable("CPSWM_UNITY_SOURCE_REVISION");
        BuildAt(destination, receiptPath, sourceRevision);
    }

    private static void BuildAt(string destination, string receiptPath, string sourceRevision) {
        if (String.IsNullOrWhiteSpace(destination) || !Path.IsPathRooted(destination)
            || !destination.EndsWith(".app", StringComparison.Ordinal)
            || Directory.Exists(destination) || File.Exists(destination)) {
            throw new InvalidOperationException("A new absolute .app output path is required.");
        }
        if (String.IsNullOrWhiteSpace(receiptPath) || !Path.IsPathRooted(receiptPath)
            || File.Exists(receiptPath) || String.IsNullOrWhiteSpace(sourceRevision)) {
            throw new InvalidOperationException("A fresh receipt path and source revision are required.");
        }
        if (Application.unityVersion != "2020.3.25f1") {
            throw new InvalidOperationException("Editor version differs from the frozen source project.");
        }
        // Same resource catalog producer as the upstream Build entry point.
        new ResourceAssetManager().BuildCatalog();
        var scenes = new[] {
            "Assets/Scenes/FloorPlan1_physics.unity",
            "Assets/Scenes/Procedural/Procedural.unity"
        };
        foreach (string scene in scenes) {
            if (!File.Exists(scene)) throw new FileNotFoundException("Real scene missing", scene);
        }
        var options = new BuildPlayerOptions {
            scenes = scenes,
            locationPathName = destination,
            target = BuildTarget.StandaloneOSX,
            options = BuildOptions.StrictMode | BuildOptions.Development | BuildOptions.CompressWithLz4
        };
        var report = BuildPipeline.BuildPlayer(options);
        var receipt = new Receipt {
            editorVersion = Application.unityVersion,
            result = report.summary.result.ToString(),
            outputPath = report.summary.outputPath,
            sourceRevision = sourceRevision,
            errors = (int)report.summary.totalErrors,
            warnings = (int)report.summary.totalWarnings
        };
        File.WriteAllText(receiptPath, JsonUtility.ToJson(receipt, true));
        // Upstream Build reads the summary but does not enforce Succeeded.
        if (report.summary.result != BuildResult.Succeeded || report.summary.totalErrors != 0) {
            throw new InvalidOperationException("Actual Unity build failed; inspect the receipt and log.");
        }
    }
}
