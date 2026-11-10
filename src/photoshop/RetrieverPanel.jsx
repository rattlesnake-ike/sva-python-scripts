// RetrieverPanel.jsx - Dockable palette that launches the AI Reference Retriever
// Runs automatically at Photoshop startup via Script Events Manager
//
// Legacy fallback - the UXP panel (uxp-plugin\) is the default front-end.
// Both read the same shared pointer file (~/production_processor_dir.txt)
// that the UXP panel keeps up to date.

#target photoshop

// Prevent duplicate panels
if (typeof RetrieverPanel !== "undefined") {
    RetrieverPanel.close();
}

// Resolve the retriever folder: shared pointer -> known locations -> pick.
function retrieverDir(pick) {
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
        if (Folder(candidates[i]).exists && File(candidates[i] + "/run.bat").exists) {
            if (cfg.open("w")) { cfg.write(candidates[i]); cfg.close(); }
            return candidates[i];
        }
    }
    if (!pick) { return null; }
    var f = Folder.selectDialog("Locate your ai-reference-retriever folder");
    if (!f) { return null; }
    if (cfg.open("w")) { cfg.write(f.fsName); cfg.close(); }
    return f.fsName;
}

var RETRIEVER_DIR = retrieverDir(false);

var RetrieverPanel = new Window("palette", "Retriever", undefined, {resizeable: true});
RetrieverPanel.orientation = "column";
RetrieverPanel.alignChildren = ["fill", "top"];
RetrieverPanel.spacing = 8;
RetrieverPanel.margins = 12;

// Title
var title = RetrieverPanel.add("statictext", undefined, "\u{1F50D} Production Processor");
title.graphics.font = ScriptUI.newFont(title.graphics.font.name, "BOLD", 13);

// Open Retriever button
var launchBtn = RetrieverPanel.add("button", undefined, "Open Retriever");
launchBtn.preferredSize.height = 36;
launchBtn.graphics.font = ScriptUI.newFont(launchBtn.graphics.font.name, "BOLD", 12);

// Open Board Folder button
var boardBtn = RetrieverPanel.add("button", undefined, "Open Board Folder");
boardBtn.preferredSize.height = 28;

// Status label
var status = RetrieverPanel.add("statictext", undefined, "", {multiline: false});
status.preferredSize.height = 18;

// Launch the retriever
launchBtn.onClick = function() {
    var dir = retrieverDir(true);
    if (!dir) { status.text = "No folder chosen"; return; }
    status.text = "Launching...";
    var vbsFile = File(dir + "/start_hidden.vbs");
    var batFile = File(dir + "/run.bat");
    if (vbsFile.exists) {
        vbsFile.execute();
    } else if (batFile.exists) {
        batFile.execute();
    } else {
        status.text = "Error: run.bat not found";
        return;
    }
    status.text = "Retriever launched!";
    app.scheduleIdleTask(function() {
        status.text = "";
    }, 5000);
};

// Open board folder
boardBtn.onClick = function() {
    var dir = retrieverDir(false);
    if (!dir) { status.text = "No folder chosen"; return; }
    var boardFolder = new Folder(dir + "/board");
    if (!boardFolder.exists) { boardFolder.create(); }
    boardFolder.execute();
    status.text = "Board folder opened";
};

// Show the panel
RetrieverPanel.show();
