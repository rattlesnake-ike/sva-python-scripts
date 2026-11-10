// BoardFolder.jsx - Open the board folder for drag-in
// Install: Copy this file to %APPDATA%\Adobe\Adobe Photoshop <version>\Presets\Scripts\
// Use: File > Scripts > BoardFolder (or bind to a keyboard shortcut)
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
            if (saved.length && Folder(saved).exists) { dir = saved; }
        }
    }
    if (!dir) {
        for (var i = 0; i < candidates.length; i++) {
            if (Folder(candidates[i]).exists) { dir = candidates[i]; break; }
        }
    }
    if (!dir) {
        var picked = Folder.selectDialog("Locate your ai-reference-retriever folder");
        if (!picked) { return; }
        dir = picked.fsName;
        if (pointer.open("w")) { pointer.write(dir); pointer.close(); }
    }

    var boardFolder = new Folder(dir + "/board");
    if (!boardFolder.exists) { boardFolder.create(); }

    var os = $.os;
    if (os.indexOf("Windows") !== -1) {
        app.system('explorer "' + boardFolder.fsName + '"');
    } else {
        app.system('open "' + boardFolder.fsName + '"');
    }
})();
