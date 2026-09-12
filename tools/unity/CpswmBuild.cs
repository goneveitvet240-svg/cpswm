// Development-only source build: real public scenes, no runtime substitutions.
using System;
using System.IO;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

public static class CpswmBuild {
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
