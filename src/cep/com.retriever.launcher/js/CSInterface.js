/* Minimal CSInterface shim: wraps the native CEP bridge (window.cep).
   Only evalScript is needed by this panel. */
function CSInterface() {}
CSInterface.prototype.evalScript = function (script, callback) {
    var cb = callback || function () {};
    try {
        if (window.cep && window.cep.util && window.cep.util.evalScript) {
            window.cep.util.evalScript(script, cb);
        } else {
            cb("CEP bridge unavailable");
        }
    } catch (e) {
        cb("error: " + e);
    }
};
