// ProductionProcessor.jsx - Launch the AI Reference Retriever
// To use: File > Scripts > ProductionProcessor
//
// Legacy fallback - the UXP panel (uxp-plugin\) is the default front-end.
// Both read the same shared pointer file (~/production_processor_dir.txt)
// that the UXP panel keeps up to date.

#target photoshop

(function () {
    var home = Folder("~").fsName;
    var candidates = [
        home + "/Downloads/ai-reference-retriever-extracted/ai-reference-retriever",
        home + "/Downloads/ai-reference-retriever",
        home + "/Desktop/ai-reference-retriever",
        home + "/Documents/ai-reference-retriever",
        home + "/ai-reference-retriever"
    ];

    var dir = null;
    var pointer = File(home + "/production_processor_dir.txt");
    if (pointer.exists) {
        pointer.open("r");
        var saved = pointer.read();
        pointer.close();
        if (saved) {
            saved = saved.replace(/[\r\n]+$/, "");
            if (saved.length && Folder(saved).exists && File(saved + "/run.bat").exists) { dir = saved; }
        }
    }
    if (!dir) {
        for (var i = 0; i < candidates.length; i++) {
            if (Folder(candidates[i]).exists && File(candidates[i] + "/run.bat").exists) { dir = candidates[i]; break; }
        }
    }
    if (!dir) {
        var picked = Folder.selectDialog("Locate your ai-reference-retriever folder");
        if (!picked) { return; }
        dir = picked.fsName;
        if (pointer.open("w")) { pointer.write(dir); pointer.close(); }
    }

    var batFile = File(dir + "/run.bat");
    var vbsFile = File(dir + "/start_hidden.vbs");
    if (vbsFile.exists) {
        vbsFile.execute();
    } else if (batFile.exists) {
        batFile.execute();
    } else {
        alert("Retriever not found in:\n" + dir);
    }
})();
