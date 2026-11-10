#requires -Version 5.1
<#
  Production Processor - unified per-user (no admin) installer.

  Installs the UXP panel (the default Photoshop front-end) plus the optional
  legacy fallbacks (JSX scripts, CEP panel) into the current user's profile.
  Nothing outside %APPDATA% or %USERPROFILE% is touched, so no UAC prompt.

  The script is portable: by default it installs the retriever that sits in
  its own folder, so the whole project can be unzipped anywhere and installed
  from there.

  Photoshop's UXP plugin manager (upic) reads a plugin registry and scans three
  folders at startup:

    registry (user) : %APPDATA%\Adobe\UXP\PluginsInfo\v1\PS.json
    system fallback : C:\Program Files\Common Files\Adobe\UXP\Plugins\External   (needs admin)
    user fallback   : %APPDATA%\Adobe\UXP\Plugins\External                      (NO admin)  <-- used here
    hybrid fallback : C:\Program Files\Common Files\Adobe\UXP\Plugins\<user>\External

  The registry entry must use the exact token form, otherwise Photoshop reports
  "Zero plugins found in user's PluginsInfo file" and skips the fallback scan:

    {"plugins":[{"hostMinVersion":"24.0.0","name":"<name>",
                 "path":"$localPlugins\\External\\<folder>",
                 "pluginId":"<id>","status":"enabled","type":"uxp","versionString":"x.y.z"}]}

  The registry file must be UTF-8 WITHOUT BOM (a BOM makes Photoshop log
  "Failed to parse JSON"). Write it with [IO.File]::WriteAllText.

  The plugin's manifest MUST declare the launchProcess permission (manifest v5),
  otherwise shell.openPath() fails and the panel cannot start the retriever.
#>

param(
    [string]$RetrieverDir = $PSScriptRoot,
    [string]$PluginId     = "com.retriever.launcher",
    [string]$PluginName   = "Production Processor",
    [switch]$SkipJsx,
    [switch]$SkipCep,
    [switch]$ResetFolder
)

$ErrorActionPreference = 'Stop'
$Stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
function Say($m) { Write-Host ("[{0}] {1}" -f $Stamp, $m) }

# --------------------------------------------------------- 0. the project ---
$configPath = Join-Path $RetrieverDir 'retriever_config.json'
if (-not (Test-Path $configPath)) {
    throw "retriever_config.json not found in '$RetrieverDir'. Run this script from inside the retriever folder."
}
$cfg = Get-Content $configPath -Raw | ConvertFrom-Json
$tool = $cfg.tool
Say "Project    : $RetrieverDir"
Say "Launcher   : $($tool.hiddenLauncher) / $($tool.launcher)"

# ------------------------------------------------------- 1. plugin source ---
# The project folder is the source of truth; a .ccx next to it is used only
# when the plugin sources are missing.
$staging = Join-Path $env:LOCALAPPDATA 'Temp\opencode\pp_install'
if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
New-Item -ItemType Directory -Path $staging -Force | Out-Null

$pluginSrc = Join-Path $RetrieverDir 'uxp-plugin'
$ccx = Join-Path $RetrieverDir 'ProductionProcessor.ccx'
if (Test-Path (Join-Path $pluginSrc 'manifest.json')) {
    Say "Using plugin source from $pluginSrc"
    # only the runtime files of the panel - the icon generator and its
    # __pycache__ stay in the project, they are not part of the plugin
    foreach ($item in @('manifest.json', 'index.html', 'index.js', 'icons')) {
        $p = Join-Path $pluginSrc $item
        if (Test-Path $p) { Copy-Item $p $staging -Recurse -Force }
    }
} elseif (Test-Path $ccx) {
    Say "Extracting $ccx"
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($ccx, $staging)
} else {
    throw "No plugin source found (uxp-plugin\manifest.json and ProductionProcessor.ccx both missing)."
}
if (-not (Test-Path (Join-Path $staging 'manifest.json'))) { throw "manifest.json not found after extraction." }

# ------------------------------------------- 2. icon scale files (1x / 2x) ---
# Keep the project's own @1x/@2x artwork when it ships them (they are drawn
# for their exact pixel size); otherwise derive them from the master icon.png.
$iconBase = 23
try {
    $m0 = Get-Content (Join-Path $staging 'manifest.json') -Raw | ConvertFrom-Json
    $firstIcon = $m0.entrypoints[0].icons | Select-Object -First 1
    if ($firstIcon -and $firstIcon.width) { $iconBase = [int]$firstIcon.width }
} catch { }

try { Add-Type -AssemblyName System.Drawing -ErrorAction Stop } catch { $iconBase = 0 }

foreach ($theme in @('dark','light')) {
    $dir = Join-Path $staging "icons\$theme"
    $src = Join-Path $dir 'icon.png'
    if (-not (Test-Path $src)) { continue }
    $one = Join-Path $dir 'icon@1x.png'
    $two = Join-Path $dir 'icon@2x.png'
    if ((Test-Path $one) -and (Test-Path $two)) {
        Say "Using the supplied 1x/2x icons for $theme"
        continue
    }
    if ($iconBase -le 0) {
        Copy-Item $src $one -Force
        Copy-Item $src $two -Force
        Say "Copied master icon for $theme"
        continue
    }
    $img = [System.Drawing.Image]::FromFile($src)
    foreach ($s in @(1, 2)) {
        $w = $iconBase * $s
        $bmp = New-Object System.Drawing.Bitmap($w, $w)
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.InterpolationMode = 'HighQualityBicubic'
        $g.PixelOffsetMode = 'HighQuality'
        $g.Clear([System.Drawing.Color]::Transparent)
        $g.DrawImage($img, 0, 0, $w, $w)
        $g.Dispose()
        $out = if ($s -eq 1) { $one } else { $two }
        $bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
        $bmp.Dispose()
    }
    $img.Dispose()
    Say "Derived ${iconBase}px 1x/2x icons for $theme"
}

# ------------------------------------------------- 3. UXP user-level install ---
$uxpTargets = @(
    (Join-Path $env:APPDATA "Adobe\UXP\Plugins\External\$PluginId"),                 # user fallback folder (primary)
    (Join-Path $env:APPDATA "Adobe\UXP\Plugins\$PluginId"),                         # user plugin folder
    (Join-Path $env:APPDATA "Adobe\UXP\PluginsStorage\PHSP\27\External\$PluginId")   # storage mirror
)
foreach ($t in $uxpTargets) {
    New-Item -ItemType Directory -Path $t -Force | Out-Null
    Copy-Item (Join-Path $staging '*') $t -Recurse -Force
}
Say "UXP panel installed -> $($uxpTargets[0])"

# ------------------------------------------ 4. plugin registry (PS.json, user) ---
$pluginsInfoDir = Join-Path $env:APPDATA 'Adobe\UXP\PluginsInfo\v1'
New-Item -ItemType Directory -Path $pluginsInfoDir -Force | Out-Null
$manifest = Get-Content (Join-Path $staging 'manifest.json') -Raw | ConvertFrom-Json
$entry = [ordered]@{
    hostMinVersion = $manifest.host.minVersion
    name           = $PluginName
    path           = "`$localPlugins\External\$PluginId"
    pluginId       = $PluginId
    status         = 'enabled'
    type           = 'uxp'
    versionString  = $manifest.version
}
$json = ([ordered]@{ plugins = @($entry) } | ConvertTo-Json -Depth 6 -Compress)
[IO.File]::WriteAllText((Join-Path $pluginsInfoDir 'PS.json'), $json, (New-Object Text.UTF8Encoding($false)))
Say "Plugin registry written -> $pluginsInfoDir\PS.json"

# ------------------------- 5. shared pointer (used by plugin, CEP and JSX) -------
# The pointer holds the folder the user picked in the panel. Once it is set it
# stays the default on this machine, so installing again must not silently
# move it somewhere else. It is only replaced when the folder it points at has
# gone away, or when -ResetFolder is passed.
$pointer = Join-Path $env:USERPROFILE $tool.pointerFile
$existing = ''
if (Test-Path $pointer) { $existing = (Get-Content $pointer -Raw).Trim() }
$keepExisting = $false
if ($existing -and -not $ResetFolder) {
    $keepExisting = Test-Path (Join-Path $existing 'retriever_config.json')
}
if ($keepExisting) {
    Say "Shared pointer kept -> $pointer ($existing)"
} else {
    if ($existing -and -not $ResetFolder) {
        Say "Shared pointer was stale ($existing) - repointing it."
    }
    [IO.File]::WriteAllText($pointer, $RetrieverDir, (New-Object Text.UTF8Encoding($false)))
    Say "Shared pointer written -> $pointer"
}

# ------------------------------------------------ 6. legacy fallbacks (opt-in) ---
if (-not $SkipJsx) {
    $psVer = Get-ChildItem "$env:APPDATA\Adobe" -Directory -Filter 'Adobe Photoshop 20*' -ErrorAction SilentlyContinue |
             Sort-Object Name -Descending | Select-Object -First 1
    if ($psVer) {
        $scripts = Join-Path $psVer.FullName 'Presets\Scripts'
        New-Item -ItemType Directory -Path $scripts -Force | Out-Null
        Copy-Item (Join-Path $RetrieverDir 'photoshop\*.jsx') $scripts -Force
        Say "JSX fallbacks installed -> $scripts"
    } else {
        Say "No Photoshop profile folder found - skipped the JSX fallbacks."
    }
}

if (-not $SkipCep) {
    $cepSrc = Join-Path $RetrieverDir 'cep\com.retriever.launcher'
    if (Test-Path $cepSrc) {
        $cepDst = Join-Path $env:APPDATA 'Adobe\CEP\extensions\com.retriever.launcher'
        New-Item -ItemType Directory -Path $cepDst -Force | Out-Null
        Copy-Item (Join-Path $cepSrc '*') $cepDst -Recurse -Force
        Say "CEP fallback installed -> $cepDst"
    }
}

# ----------------------------------------------------------------- done -----
Say "DONE."
Say "1) Restart Photoshop."
Say "2) Plugins > Production Processor > Retriever  (default front-end)"
Say "3) First 'Open Retriever' click shows a UXP consent prompt - choose Allow."
