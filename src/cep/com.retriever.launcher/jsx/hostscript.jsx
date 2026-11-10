// hostscript.jsx - auto-loaded by the Retriever CEP panel (ES3 only).
//
// The CEP panel is a legacy fallback: the UXP panel (uxp-plugin\) is the
// default Photoshop front-end. Both read the same shared pointer file
// (~/production_processor_dir.txt), which the UXP panel keeps up to date, so
// there is exactly one place that knows where the retriever lives.

// Resolve the retriever folder: shared pointer -> known locations -> pick.
function productionProcessorDir(pick) {
    var home = Folder("~").fsName;
    var candidates = [
        home + "/Downloads/ai-reference-retriever-extracted/ai-reference-retriever",
        home + "/Downloads/ai-reference-retriever",
        home + "/Desktop/ai-reference-retriever",
        home + "/Documents/ai-reference-retriever",
        home + "/ai-reference-retriever"
    ];

    var cfg = File(home + "/production_processor_dir.txt");
    if (cfg.exists) {
        cfg.open("r");
        var saved = cfg.read();
        cfg.close();
        if (saved) {
            saved = saved.replace(/[\r\n]+$/, "");
            if (saved.length && Folder(saved).exists && File(saved + "/run.bat").exists) { return saved; }
        }
    }
    for (var i = 0; i < candidates.length; i++) {
        var dir = candidates[i];
        if (Folder(dir).exists && File(dir + "/run.bat").exists) {
            if (cfg.open("w")) { cfg.write(dir); cfg.close(); }
            return dir;
        }
    }
    if (!pick) { return null; }
    var f = Folder.selectDialog("Locate your ai-reference-retriever folder");
    if (!f) { return null; }
    if (cfg.open("w")) { cfg.write(f.fsName); cfg.close(); }
    return f.fsName;
}
function productionProcessorLaunch() {
    var dir = productionProcessorDir(true);
    if (!dir) { return "cancelled - no folder chosen"; }
    var vbs = File(dir + "/start_hidden.vbs");
    if (vbs.exists) { vbs.execute(); return "retriever launching..."; }
    File(dir + "/run.bat").execute();
    return "retriever launching...";
}
function productionProcessorBoard() {
    var dir = productionProcessorDir(false);
    if (!dir) { return "open the Retriever once first"; }
    var board = Folder(dir + "/board");
    if (!board.exists) { board.create(); }
    board.execute();
    return "";
}
