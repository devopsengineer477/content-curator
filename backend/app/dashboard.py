"""
Single-page dashboard.

Deliberately dependency-free (no CDN, no build step) so it renders identically
in the in-app preview sandbox and in any browser. The Next.js frontend in the
architecture doc talks to the exact same /api endpoints.
"""

DASHBOARD_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#0a0e14">
<title>Tech Content Curator</title>
<script>
  // Resolve the theme before first paint so the page never flashes the wrong
  // colours. Kept inline and synchronous for exactly that reason.
  (function(){
    var t = null;
    try { t = localStorage.getItem('tc-theme'); } catch(e){}
    if(t !== 'light' && t !== 'dark'){
      t = matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
    }
    document.documentElement.dataset.theme = t;
    var m = document.querySelector('meta[name="theme-color"]');
    if(m) m.content = t === 'light' ? '#f4f6fa' : '#0a0e14';
  })();
</script>
<style>
  :root{
    /* ---- dark (default) ---- */
    --bg:#0a0e14; --sunken:#0c121b; --sunken2:#0a0f17;
    --panel:#111823; --panel2:#151d2a; --raise:#0f1723; --raise2:#16202e;
    --line:#1f2a38; --line2:#18222f; --hover:#31415a;
    --txt:#e6edf3; --muted:#8b98a5; --dim:#7d8b99;
    --accent:#6ea8fe; --accent2:#7ee787; --warn:#f0b72f; --danger:#f85149;
    --hot:#ff7b72; --warm:#f0b72f; --cool:#6ea8fe; --cold:#6e7d8c;
    --sel:#1b2b45; --sel-bd:#2f4a75; --sel-tx:#cfe1ff;
    --tag-bg:#16202e; --tag-tx:#9fb3c8;
    --input-bg:#0a0f17; --input-bd:#2b3a4e;
    --shadow:0 8px 30px rgba(0,0,0,.5);
    --scroll:#243141;
    --topbar:linear-gradient(180deg,#101825,#0d141d);
    --btn-hover:#1b2534; --btn-hover-bd:#2c3a4d;
    --sect-bd:#1d2937;
    --bar-off:#1a2331;
    --summary:#c6d3e0; --code-tx:#d8e2ec; --install-tx:#b9c7d6;
    --cat-bg:#152233; --cat-tx:#8ab4ff;
    --warm-bg:#3a2f14; --cool-bg:#152b45; --cold-bg:#1b232e;
    --ok-bg:#0f2e1c; --err-bg:#3a1d1d; --warn-bg:#2a2416;
    --glow:rgba(255,255,255,.35);
    --radius:10px;
    color-scheme:dark;
  }
  :root[data-theme="light"]{
    /* ---- light ---- */
    --bg:#f4f6fa; --sunken:#e9eef5; --sunken2:#f8fafc;
    --panel:#ffffff; --panel2:#f0f4f9; --raise:#ffffff; --raise2:#eef3f9;
    --line:#d5dde7; --line2:#e2e8f0; --hover:#b9c6d6;
    --txt:#15202b; --muted:#55677a; --dim:#64748b;
    --accent:#1d4ed8; --accent2:#15803d; --warn:#a16207; --danger:#cf222e;
    --hot:#cf222e; --warm:#a16207; --cool:#1d4ed8; --cold:#64748b;
    --sel:#dbeafe; --sel-bd:#93b4f5; --sel-tx:#1e40af;
    --tag-bg:#e6edf6; --tag-tx:#4a5b6e;
    --input-bg:#ffffff; --input-bd:#c3d0e0;
    --scroll:#c3cfdd;
    --topbar:linear-gradient(180deg,#ffffff,#f1f5f9);
    --btn-hover:#e8eef6; --btn-hover-bd:#c3d0e0;
    --sect-bd:#d5dde7;
    --bar-off:#e2e8f0;
    --summary:#334155; --code-tx:#1e293b; --install-tx:#55677a;
    --cat-bg:#e0e7ff; --cat-tx:#3730a3;
    --warm-bg:#fef3c7; --cool-bg:#dbeafe; --cold-bg:#e8edf3;
    --ok-bg:#dcfce7; --err-bg:#fee2e2; --warn-bg:#fef3c7;
    --glow:rgba(15,23,42,.28);
    --shadow:0 8px 30px rgba(15,23,42,.18);
    color-scheme:light;
  }
  *{box-sizing:border-box}
  /* The `hidden` attribute is implemented as a UA-stylesheet `display:none`,
     which ANY author `display` rule silently overrides. .board and .toolbar
     both set display, so without this the tab switch would leave them on
     screen and stack Settings underneath instead of replacing the board. */
  [hidden]{display:none !important}
  html,body{margin:0;height:100%}
  body{
    background:var(--bg); color:var(--txt);
    font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    -webkit-font-smoothing:antialiased;
  }
  button{font:inherit;cursor:pointer}
  a{color:var(--accent);text-decoration:none}
  a:hover{text-decoration:underline}
  ::-webkit-scrollbar{width:10px;height:10px}
  ::-webkit-scrollbar-thumb{background:var(--scroll);border-radius:6px}
  ::-webkit-scrollbar-track{background:transparent}

  /* ---------- top bar ---------- */
  .topbar{
    display:flex;align-items:center;gap:18px;padding:12px 18px;
    background:var(--topbar);
    border-bottom:1px solid var(--line);position:sticky;top:0;z-index:30;
  }
  .brand{display:flex;align-items:center;gap:11px;min-width:0}
  .logo{
    width:34px;height:34px;border-radius:9px;display:grid;place-items:center;
    background:linear-gradient(135deg,#6ea8fe,#a371f7);color:#08111d;
    font-weight:800;font-size:13px;letter-spacing:.5px;flex:none;
  }
  .brand-title{font-weight:650;font-size:15px;letter-spacing:.2px}
  .brand-sub{font-size:11.5px;color:var(--muted);margin-top:-2px}
  .pills{display:flex;gap:8px;flex-wrap:wrap;margin-left:auto}
  .pill{
    background:var(--panel2);border:1px solid var(--line);border-radius:999px;
    padding:4px 11px;font-size:11.5px;color:var(--muted);white-space:nowrap;
  }
  .pill b{color:var(--txt);font-weight:650}
  .pill.good b{color:var(--accent2)}
  .pill.warn b{color:var(--warn)}
  .actions{display:flex;gap:8px;flex:none}
  .btn{
    background:var(--panel2);color:var(--txt);border:1px solid var(--line);
    border-radius:8px;padding:7px 13px;font-size:12.5px;font-weight:550;
    transition:.15s;white-space:nowrap;
  }
  .btn:hover{background:var(--btn-hover);border-color:var(--btn-hover-bd)}
  .btn:disabled{opacity:.5;cursor:not-allowed}
  .btn-primary{background:linear-gradient(180deg,#3b82f6,#2563eb);border-color:#2563eb;color:#fff}
  .btn-primary:hover{background:linear-gradient(180deg,#4f8ff8,#2f6ff0)}
  .btn-ghost{background:transparent}
  .btn-sm{padding:4px 9px;font-size:11.5px;border-radius:6px}

  /* ---------- stats strip ---------- */
  .stats{display:flex;gap:0;border-bottom:1px solid var(--line);background:var(--sunken)}
  .stat{flex:1;padding:10px 18px;border-right:1px solid var(--line);min-width:0}
  .stat:last-child{border-right:none}
  .stat-k{font-size:10.5px;text-transform:uppercase;letter-spacing:.7px;color:var(--dim)}
  .stat-v{font-size:19px;font-weight:680;margin-top:1px;font-variant-numeric:tabular-nums}
  .stat-v small{font-size:11px;font-weight:500;color:var(--muted)}

  /* ---------- toolbar ---------- */
  .toolbar{
    display:flex;align-items:center;gap:8px;padding:10px 18px;flex-wrap:wrap;
    border-bottom:1px solid var(--line);background:var(--sunken);
  }
  .input{
    background:var(--panel);border:1px solid var(--line);color:var(--txt);
    border-radius:8px;padding:7px 10px;font-size:12.5px;outline:none;
  }
  .input:focus{border-color:var(--accent)}
  #search{width:260px}
  .chips{display:flex;gap:5px;flex-wrap:wrap}
  .chip{
    background:transparent;border:1px solid var(--line);color:var(--muted);
    border-radius:999px;padding:3px 10px;font-size:11.5px;transition:.15s;
  }
  .chip:hover{color:var(--txt);border-color:var(--hover)}
  .chip.on{background:var(--sel);border-color:var(--sel-bd);color:var(--sel-tx)}
  .check{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--muted);cursor:pointer}

  /* ---------- board ---------- */
  .board{
    display:grid;grid-template-columns:repeat(4,minmax(255px,1fr));
    gap:12px;padding:14px 18px 40px;align-items:start;
  }
  @media (max-width:900px){.board{grid-template-columns:repeat(2,minmax(0,1fr))}}
  @media (max-width:560px){.board{grid-template-columns:1fr}}
  .col{background:var(--sunken);border:1px solid var(--line);border-radius:var(--radius);min-height:180px}
  .col-h{
    display:flex;align-items:center;gap:8px;padding:10px 12px;
    border-bottom:1px solid var(--line);position:sticky;top:0;
  }
  .dot{width:8px;height:8px;border-radius:50%;flex:none}
  .col-t{font-size:12px;font-weight:650;letter-spacing:.4px;text-transform:uppercase}
  .col-n{margin-left:auto;font-size:11px;color:var(--dim);font-variant-numeric:tabular-nums}
  .col-b{padding:8px;display:flex;flex-direction:column;gap:8px}
  .empty{padding:22px 10px;text-align:center;color:var(--dim);font-size:12px}

  .card{
    background:var(--panel);border:1px solid var(--line);border-radius:8px;
    padding:10px 11px;cursor:pointer;transition:.14s;position:relative;
  }
  .card:hover{border-color:var(--hover);background:var(--panel2);transform:translateY(-1px)}
  .card-t{font-size:13px;font-weight:570;line-height:1.35;margin-bottom:6px}
  .card-m{display:flex;align-items:center;gap:6px;font-size:11px;color:var(--dim);flex-wrap:wrap}
  .card-f{display:flex;gap:4px;flex-wrap:wrap;margin:7px 0 0}
  .tag{
    background:var(--raise2);color:var(--tag-tx);border-radius:4px;padding:1px 6px;
    font-size:10.5px;border:1px solid var(--sect-bd);
  }
  .cat{background:var(--cat-bg);color:var(--cat-tx);border-radius:4px;padding:1px 6px;font-size:10.5px}
  .prio{
    display:inline-flex;align-items:center;gap:4px;font-size:10.5px;font-weight:700;
    padding:1px 7px;border-radius:999px;font-variant-numeric:tabular-nums;
  }
  .prio-hot{background:var(--err-bg);color:var(--hot)}
  .prio-warm{background:var(--warm-bg);color:var(--warm)}
  .prio-cool{background:var(--cool-bg);color:var(--cool)}
  .prio-cold{background:var(--cold-bg);color:var(--cold)}
  .card-x{display:flex;gap:3px;margin-top:8px;opacity:0;transition:.14s}
  .card:hover .card-x{opacity:1}
  .xbtn{
    background:var(--raise);border:1px solid var(--line);color:var(--muted);
    border-radius:5px;padding:2px 7px;font-size:11px;line-height:1.4;
  }
  .xbtn:hover{color:var(--txt);border-color:var(--hover)}
  .dupe-flag{
    position:absolute;top:-1px;right:-1px;background:var(--warn-bg);color:var(--warn);
    font-size:9.5px;padding:1px 6px;border-radius:0 7px 0 6px;font-weight:700;
  }

  /* ---------- drawer ---------- */
  .scrim{
    position:fixed;inset:0;background:rgba(3,6,11,.6);z-index:40;
    opacity:0;pointer-events:none;transition:.2s;
  }
  .scrim.on{opacity:1;pointer-events:auto}
  .drawer{
    position:fixed;top:0;right:0;bottom:0;width:min(560px,100%);z-index:50;
    background:var(--sunken);border-left:1px solid var(--line);display:flex;flex-direction:column;
    transform:translateX(102%);transition:transform .22s cubic-bezier(.4,0,.2,1);
  }
  .drawer.on{transform:none}
  .dr-h{padding:14px 16px;border-bottom:1px solid var(--line);display:flex;gap:10px;align-items:flex-start}
  .dr-t{font-size:15px;font-weight:650;line-height:1.35;flex:1}
  .dr-b{overflow-y:auto;padding:14px 16px;flex:1}
  .dr-f{padding:11px 16px;border-top:1px solid var(--line);display:flex;gap:6px;flex-wrap:wrap}
  .sect{margin-bottom:16px}
  .sect-h{
    font-size:10.5px;text-transform:uppercase;letter-spacing:.8px;color:var(--dim);
    margin-bottom:7px;display:flex;align-items:center;gap:8px;
  }
  .sect-h:after{content:"";flex:1;height:1px;background:var(--line)}
  .meta{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px}
  .summary{color:var(--summary);font-size:13px;line-height:1.6}
  .kv{display:flex;justify-content:space-between;font-size:12px;padding:3px 0;border-bottom:1px dashed var(--line2)}
  .kv span:first-child{color:var(--dim)}
  .kv span:last-child{font-variant-numeric:tabular-nums}
  .rel{
    display:flex;gap:8px;align-items:center;padding:6px 8px;border-radius:6px;
    background:var(--panel);border:1px solid var(--line);margin-bottom:5px;font-size:12px;
  }
  .rel-sim{margin-left:auto;font-size:11px;color:var(--accent2);font-variant-numeric:tabular-nums}
  .bar{height:6px;background:var(--raise2);border-radius:4px;overflow:hidden;margin-top:5px}
  .bar>i{display:block;height:100%;border-radius:4px}
  textarea{
    width:100%;min-height:150px;background:var(--sunken2);border:1px solid var(--line);
    color:var(--code-tx);border-radius:8px;padding:10px;font:12px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
    resize:vertical;outline:none;
  }
  textarea:focus{border-color:var(--accent)}
  .draft{border:1px solid var(--line);border-radius:8px;background:var(--panel);margin-bottom:10px;overflow:hidden}
  .draft-h{display:flex;align-items:center;gap:8px;padding:7px 10px;background:var(--raise);border-bottom:1px solid var(--line)}
  .draft-h b{font-size:12px}
  .prov{font-size:10px;color:var(--dim);margin-left:auto}
  .draft-b{padding:10px}
  details summary{cursor:pointer;color:var(--muted);font-size:12px;padding:5px 0}
  pre{
    white-space:pre-wrap;word-break:break-word;background:var(--sunken2);border:1px solid var(--line);
    border-radius:8px;padding:10px;font:11.5px/1.55 ui-monospace,Menlo,Consolas,monospace;
    color:var(--install-tx);max-height:260px;overflow:auto;
  }
  .toast{
    position:fixed;bottom:18px;left:50%;transform:translate(-50%,20px);z-index:80;
    background:var(--raise2);border:1px solid var(--input-bd);color:var(--txt);border-radius:9px;
    padding:9px 15px;font-size:12.5px;opacity:0;pointer-events:none;transition:.22s;
    box-shadow:var(--shadow);max-width:80vw;
  }
  .toast.on{opacity:1;transform:translate(-50%,0)}
  .spin{
    width:11px;height:11px;border:2px solid currentColor;border-top-color:transparent;opacity:.85;
    border-radius:50%;display:inline-block;animation:sp .7s linear infinite;vertical-align:-1px;
  }
  @keyframes sp{to{transform:rotate(360deg)}}
  .sect-btns{display:flex;gap:5px;flex-wrap:wrap;margin-bottom:10px}

  /* ---------- nav ---------- */
  .nav{display:flex;gap:2px;background:var(--raise);border:1px solid var(--line);border-radius:8px;padding:2px}
  .navbtn{
    background:transparent;border:none;color:var(--muted);border-radius:6px;
    padding:5px 13px;font-size:12.5px;font-weight:550;transition:.15s;
  }
  .navbtn:hover{color:var(--txt)}
  .navbtn.on{background:var(--sel);color:var(--sel-tx)}

  /* ---------- settings ---------- */
  .settings{padding:18px;max-width:1000px;margin:0 auto}
  .set-head{display:flex;align-items:flex-start;gap:16px;margin-bottom:16px;flex-wrap:wrap}
  .set-head h2{margin:0 0 3px;font-size:17px;font-weight:650}
  .set-head p{margin:0;font-size:12.5px;color:var(--muted);max-width:520px}
  .set-actions{margin-left:auto;display:flex;gap:7px}
  .status-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(215px,1fr));gap:10px;margin-bottom:20px}
  .status-card{background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:11px 13px}
  .status-k{font-size:10.5px;text-transform:uppercase;letter-spacing:.7px;color:var(--dim);margin-bottom:5px}
  .status-v{font-size:13.5px;font-weight:600;display:flex;align-items:center;gap:7px}
  .status-d{font-size:11.5px;color:var(--muted);margin-top:3px}
  .dotstate{width:8px;height:8px;border-radius:50%;flex:none}
  .dotstate.ok{background:var(--accent2);box-shadow:0 0 7px var(--glow)}
  .dotstate.warn{background:var(--warn);box-shadow:0 0 7px var(--glow)}
  .dotstate.bad{background:var(--danger);box-shadow:0 0 7px var(--glow)}
  .set-group{margin-bottom:18px}
  .set-group-h{
    font-size:11px;text-transform:uppercase;letter-spacing:.9px;color:var(--dim);
    margin-bottom:8px;display:flex;align-items:center;gap:9px;
  }
  .set-group-h:after{content:"";flex:1;height:1px;background:var(--line)}
  .set-card{background:var(--panel);border:1px solid var(--line);border-radius:9px;overflow:hidden}
  .set-row{
    display:grid;grid-template-columns:minmax(190px,240px) 1fr;gap:14px;
    padding:11px 14px;border-bottom:1px solid var(--line2);align-items:start;
  }
  .set-row:last-child{border-bottom:none}
  .set-lab{font-size:12.5px;font-weight:550}
  .set-lab .tag{margin-left:6px}
  .set-help{font-size:11px;color:var(--dim);margin-top:3px;line-height:1.45}
  .set-ctl{display:flex;flex-direction:column;gap:6px}
  .set-ctl select,.set-ctl input[type=text],.set-ctl input[type=number],.set-ctl input[type=password]{
    background:var(--sunken2);border:1px solid var(--line);color:var(--txt);border-radius:7px;
    padding:7px 10px;font-size:12.5px;outline:none;width:100%;max-width:340px;
  }
  .set-ctl select:focus,.set-ctl input:focus{border-color:var(--accent)}
  .set-ctl textarea{min-height:88px}
  .set-row.hero .set-lab{font-size:13px;font-weight:650}
  .set-row.hero select{font-weight:600}
  .install{
    font-size:11px;color:var(--tag-tx);background:var(--raise);border:1px solid var(--line);
    border-left:2px solid var(--warn);border-radius:0 6px 6px 0;padding:7px 10px;
    font-family:ui-monospace,Menlo,Consolas,monospace;white-space:pre-wrap;
  }
  .install.ok{border-left-color:var(--accent2)}

  /* ---------- sources ---------- */
  .src-add{display:flex;gap:7px;padding:11px 14px;border-bottom:1px solid var(--line2);flex-wrap:wrap}
  .src-add .input{width:auto;flex:1;min-width:130px}
  .src-row{
    display:grid;grid-template-columns:1fr auto auto auto;gap:10px;align-items:center;
    padding:9px 14px;border-bottom:1px solid var(--line2);
  }
  .src-row:last-child{border-bottom:none}
  .src-row.off{opacity:.45}
  .src-name{font-size:12.5px;font-weight:570;display:flex;align-items:center;gap:7px}
  .src-meta{font-size:11px;color:var(--dim);margin-top:2px;word-break:break-all}
  .src-stats{display:flex;gap:9px;align-items:center;font-size:11px;color:var(--muted);white-space:nowrap}
  .src-health{font-size:10.5px;padding:1px 7px;border-radius:999px;white-space:nowrap}
  .src-health.ok{background:var(--ok-bg);color:var(--accent2)}
  .src-health.err{background:var(--err-bg);color:var(--hot)}
  .src-health.never{background:var(--cold-bg);color:var(--cold)}
  .src-act{display:flex;gap:5px;align-items:center}
  .src-badge{font-size:9.5px;background:var(--warn-bg);color:var(--warn);padding:1px 5px;border-radius:4px}
  .src-empty{padding:20px;text-align:center;color:var(--dim);font-size:12px}
</style>
</head>
<body>

<header class="topbar">
  <div class="brand">
    <div class="logo">TC</div>
    <div>
      <div class="brand-title">Tech Content Curator</div>
      <div class="brand-sub">curate &middot; classify &middot; dedupe &middot; create</div>
    </div>
  </div>
  <nav class="nav" id="nav">
    <button class="navbtn on" data-view="board">Board</button>
    <button class="navbtn" data-view="settings">Settings</button>
  </nav>
  <div class="pills" id="pills"></div>
  <div class="actions">
    <button class="btn btn-ghost btn-sm" id="btn-theme" title="Switch between light and dark">&#9789; <span id="theme-label">Dark</span></button>
    <button class="btn btn-primary" id="btn-ingest">&#8635; Run ingestion</button>
  </div>
</header>

<section class="stats" id="stats"></section>

<div class="toolbar" id="toolbar">
  <input class="input" id="search" placeholder="Search titles, tags, summaries&hellip;">
  <select class="input" id="f-source"></select>
  <select class="input" id="f-diff">
    <option value="">Any difficulty</option>
    <option value="beginner">Beginner</option>
    <option value="intermediate">Intermediate</option>
    <option value="advanced">Advanced</option>
  </select>
  <select class="input" id="f-sort">
    <option value="newest">Sort: newest first</option>
    <option value="priority">Sort: priority</option>
    <option value="trending">Sort: trending</option>
  </select>
  <label class="check"><input type="checkbox" id="f-dupes"> duplicates</label>
  <div class="chips" id="chips"></div>
</div>

<main class="board" id="board"></main>

<!-- ================= SETTINGS VIEW ================= -->
<section class="settings" id="settings-view" hidden>
  <div class="set-head">
    <div>
      <h2>Settings</h2>
      <p id="set-note">Changes are saved to the database and survive a restart.</p>
    </div>
    <div class="set-actions">
      <button class="btn btn-ghost btn-sm" id="btn-reset-settings">Reset to defaults</button>
      <button class="btn btn-primary" id="btn-save-settings">Save changes</button>
    </div>
  </div>
  <div class="status-row" id="backend-status"></div>
  <div id="set-groups"></div>

  <!-- ================= SOURCES ================= -->
  <div class="set-group">
    <div class="set-group-h">Sources &mdash; feeds being monitored</div>
    <div class="set-card">
      <div class="src-add">
        <input class="input" id="src-name" placeholder="Name, e.g. Netflix TechBlog">
        <input class="input" id="src-url" placeholder="https://example.com/feed" style="flex:2">
        <select class="input" id="src-cat"></select>
        <input class="input" id="src-auth" type="number" min="0" max="1" step="0.05"
               value="0.7" title="Authority 0-1" style="max-width:96px">
        <button class="btn btn-primary btn-sm" id="btn-add-source">Add feed</button>
      </div>
      <div id="src-list"></div>
    </div>
  </div>
</section>

<div class="scrim" id="scrim"></div>
<aside class="drawer" id="drawer">
  <div class="dr-h">
    <div class="dr-t" id="dr-title">&mdash;</div>
    <button class="btn btn-sm btn-ghost" id="dr-close">&#10005;</button>
  </div>
  <div class="dr-b" id="dr-body"></div>
  <div class="dr-f" id="dr-foot"></div>
</aside>

<div class="toast" id="toast"></div>

<script>
const $ = s => document.querySelector(s);
const COLS = [
  {id:'new',       label:'New',        color:'#6ea8fe'},
  {id:'reviewing', label:'Reviewing',  color:'#f0b72f'},
  {id:'drafted',   label:'Drafted',    color:'#a371f7'},
  {id:'published', label:'Published',  color:'#7ee787'},
];
const FMT = {blog:'Blog post', linkedin:'LinkedIn', twitter:'X thread', newsletter:'Newsletter'};

const state = {
  status:'all', category:'', source:'', difficulty:'', q:'', sort:'newest',
  dupes:false, articles:[], selected:null, stats:null, sources:[], view:'board',
  settings:null,
};

/* ---------------- helpers ---------------- */
function band(p){ return p>=75?'hot':p>=50?'warm':p>=25?'cool':'cold'; }
function esc(s){ return (s==null?'':String(s)).replace(/[&<>"']/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function ago(iso){
  if(!iso) return '';
  const d = new Date(iso), s = (Date.now()-d.getTime())/1000;
  if(s<60) return 'just now';
  if(s<3600) return Math.floor(s/60)+'m ago';
  if(s<86400) return Math.floor(s/3600)+'h ago';
  const days = Math.floor(s/86400);
  if(days<30) return days+'d ago';
  return d.toLocaleDateString();
}
let toastT;
function toast(msg, ms){
  const t = $('#toast'); t.innerHTML = msg; t.classList.add('on');
  clearTimeout(toastT); toastT = setTimeout(()=>t.classList.remove('on'), ms||3200);
}

/* ---------------- data ---------------- */
async function api(path, opts){
  const r = await fetch(path, opts);
  if(!r.ok){
    let detail = r.statusText || String(r.status);
    try {
      const j = await r.json();
      const d = j && j.detail;
      // FastAPI puts field errors in detail as {field: message}
      detail = (d && typeof d === 'object')
        ? Object.entries(d).map(([k,v])=>k+': '+v).join(' · ')
        : (d || detail);
    } catch(_){}
    const err = new Error(detail); err.detail = detail; throw err;
  }
  return r.json();
}

async function loadStats(){
  state.stats = await api('/api/stats');
  renderStats(); renderPills(); renderChips(); renderSources();
}
async function loadSources(){
  const d = await api('/api/sources');
  state.sources = d.items;
  renderSources();
}
async function loadArticles(){
  const p = new URLSearchParams({
    sort: state.sort, limit: 200,
    include_duplicates: state.dupes,
  });
  if(state.status !== 'all') p.set('status', state.status);
  if(state.category) p.set('category', state.category);
  if(state.source) p.set('source', state.source);
  if(state.difficulty) p.set('difficulty', state.difficulty);
  if(state.q) p.set('q', state.q);
  const d = await api('/api/articles?' + p);
  state.articles = d.items;
  renderBoard();
}

/* ---------------- render ---------------- */
function renderStats(){
  const s = state.stats; if(!s) return;
  const maxT = Math.max(1, ...s.timeline.map(t=>t.n));
  const bars = s.timeline.map(t=>{
    const h = Math.round(t.n/maxT*100);
    return `<div style="flex:1;display:flex;flex-direction:column;justify-content:flex-end;height:100%" title="${t.day}: ${t.n}">
      <div style="height:${Math.max(h,2)}%;background:${t.n?'linear-gradient(180deg,var(--cool),var(--accent))':'var(--bar-off)'};border-radius:2px 2px 0 0"></div>
    </div>`;
  }).join('');
  const feedOk = s.sources_ok, feedAll = s.sources.length;
  $('#stats').innerHTML = `
    <div class="stat"><div class="stat-k">Articles</div><div class="stat-v">${s.total}</div></div>
    <div class="stat"><div class="stat-k">Avg priority</div><div class="stat-v">${s.avg_priority}<small>/100</small></div></div>
    <div class="stat"><div class="stat-k">Duplicates merged</div><div class="stat-v" style="color:var(--warn)">${s.duplicates}</div></div>
    <div class="stat"><div class="stat-k">Feeds healthy</div><div class="stat-v" style="color:${feedOk===feedAll?'var(--accent2)':'var(--warn)'}">${feedOk}<small>/${feedAll}</small></div></div>
    <div class="stat"><div class="stat-k">Drafts</div><div class="stat-v">${s.drafts}</div></div>
    <div class="stat"><div class="stat-k">Engine</div><div class="stat-v" style="font-size:13px;padding-top:5px">${s.llm_enabled?'LLM · '+esc(s.llm):'Heuristic'}<small> / ${esc(s.embedder)}</small></div></div>
    <div class="stat" style="max-width:170px"><div class="stat-k">Intake · 14d</div>
      <div style="display:flex;gap:2px;align-items:flex-end;height:26px;margin-top:2px">${bars}</div></div>`;
}

function renderPills(){
  const s = state.stats; if(!s) return;
  const b = s.by_status;
  $('#pills').innerHTML =
    `<span class="pill">new <b>${b.new||0}</b></span>
     <span class="pill">reviewing <b>${b.reviewing||0}</b></span>
     <span class="pill">drafted <b>${b.drafted||0}</b></span>
     <span class="pill">published <b>${b.published||0}</b></span>`;
}

function renderChips(){
  const cats = (state.stats && state.stats.categories) || [];
  const chips = [`<button class="chip ${state.category===''?'on':''}" data-cat="">All</button>`]
    .concat(cats.map(c=>
      `<button class="chip ${state.category===c.category?'on':''}" data-cat="${esc(c.category)}">${esc(c.category)} <b style="color:var(--dim)">${c.n}</b></button>`));
  $('#chips').innerHTML = chips.join('');
  $('#chips').querySelectorAll('.chip').forEach(el=>{
    el.onclick = ()=>{ state.category = el.dataset.cat; loadArticles(); renderChips(); };
  });
}

function renderSources(){
  const sel = $('#f-source');
  const cur = state.source;
  sel.innerHTML = '<option value="">All sources</option>' +
    (state.stats ? state.stats.sources : []).map(s=>
      `<option value="${s.id}">${esc(s.name)} (${s.articles})</option>`).join('');
  sel.value = cur;
}

function card(a){
  const b = band(a.priority_score);
  const tags = (a.tags||[]).slice(0,3).map(t=>`<span class="tag">${esc(t)}</span>`).join('');
  const cats = (a.categories||[]).slice(0,2).map(c=>`<span class="cat">${esc(c)}</span>`).join('');
  const idx = COLS.findIndex(c=>c.id===a.status);
  const prev = COLS[idx-1], next = COLS[idx+1];
  return `<div class="card" data-id="${a.id}">
    ${a.duplicate_of!=null?'<div class="dupe-flag">DUP</div>':''}
    <div class="card-t">${esc(a.title)}</div>
    <div class="card-m">
      <span class="prio prio-${b}">${a.priority_score}</span>
      <span>${esc(a.source_name||'')}</span><span>&middot;</span><span>${ago(a.published_at||a.scraped_at)}</span>
      ${a.cluster_size>1?`<span style="color:var(--accent2)">&middot; &times;${a.cluster_size} sources</span>`:''}
    </div>
    <div class="card-f">${cats}${tags}</div>
    <div class="card-x">
      ${prev?`<button class="xbtn" data-move="${prev.id}" title="Move to ${prev.label}">&lsaquo;</button>`:''}
      ${next?`<button class="xbtn" data-move="${next.id}" title="Move to ${next.label}">&rsaquo;</button>`:''}
      <button class="xbtn" data-open="${a.id}" style="margin-left:auto">open</button>
    </div>
  </div>`;
}

function renderBoard(){
  const byStatus = {};
  COLS.forEach(c=>byStatus[c.id]=[]);
  state.articles.forEach(a=>{ (byStatus[a.status]||byStatus.new).push(a); });
  $('#board').innerHTML = COLS.map(c=>`
    <div class="col">
      <div class="col-h">
        <span class="dot" style="background:${c.color}"></span>
        <span class="col-t">${c.label}</span>
        <span class="col-n">${byStatus[c.id].length}</span>
      </div>
      <div class="col-b">
        ${byStatus[c.id].length
          ? byStatus[c.id].map(card).join('')
          : `<div class="empty">Nothing here.<br><span style="color:var(--dim)">Run ingestion or widen filters.</span></div>`}
      </div>
    </div>`).join('');

  $('#board').querySelectorAll('.card').forEach(el=>{
    el.onclick = e=>{
      const mv = e.target.dataset && e.target.dataset.move;
      if(mv){ e.stopPropagation(); move(el.dataset.id, mv); return; }
      open(el.dataset.id);
    };
  });
}

async function move(id, status){
  try{
    await api('/api/articles/'+id, {method:'PATCH',
      headers:{'Content-Type':'application/json'}, body:JSON.stringify({status})});
    const a = state.articles.find(x=>x.id==id);
    if(a) a.status = status;
    renderBoard(); loadStats();
  }catch(e){ toast('Move failed: '+e.message); }
}

/* ---------------- drawer ---------------- */
async function open(id){
  state.selected = id;
  const d = await api('/api/articles/'+id);
  const a = d.article;
  $('#dr-title').innerHTML = esc(a.title);
  const b = band(a.priority_score);
  const related = (d.related||[]).map(r=>
    `<div class="rel"><span>${esc(r.title)}</span><span class="rel-sim">${(r.similarity*100).toFixed(0)}%</span></div>`).join('')
    || '<div class="empty">No related coverage found.</div>';

  $('#dr-body').innerHTML = `
    <div class="meta">
      <span class="prio prio-${b}">priority ${a.priority_score}</span>
      <span class="cat">${esc((a.categories||[])[0]||'general-dev')}</span>
      <span class="tag">${esc(a.difficulty)}</span>
      ${(a.categories||[]).slice(1).map(c=>`<span class="cat">${esc(c)}</span>`).join('')}
    </div>
    <div class="sect">
      <div class="sect-h">Summary</div>
      <div class="summary">${esc(a.summary||'(none)')}</div>
    </div>
    <div class="sect">
      <div class="sect-h">Signals</div>
      <div class="kv"><span>Trending score</span><span>${a.trending_score} / 10</span></div>
      <div class="kv"><span>Novelty (1 &minus; max similarity)</span><span>${(a.novelty*100).toFixed(0)}%</span></div>
      <div class="kv"><span>Cluster size</span><span>${a.cluster_size} article(s)</span></div>
      <div class="kv"><span>Words</span><span>${a.word_count}</span></div>
      <div class="kv"><span>Source</span><span>${esc(a.source_name||'')} &middot; authority ${a.authority||0}</span></div>
      <div class="kv"><span>Published</span><span>${ago(a.published_at)}</span></div>
      <div class="bar"><i style="width:${Math.min(100,a.priority_score)}%;background:${
        b==='hot'?'var(--hot)':b==='warm'?'var(--warm)':b==='cool'?'var(--cool)':'var(--cold)'}"></i></div>
    </div>
    <div class="sect">
      <div class="sect-h">Tags</div>
      <div class="card-f">${(a.tags||[]).map(t=>`<span class="tag">${esc(t)}</span>`).join('')||'<span class="empty">none</span>'}</div>
    </div>
    <div class="sect">
      <div class="sect-h">Related coverage (RAG context)</div>
      ${related}
    </div>
    ${d.duplicates && d.duplicates.length ? `
    <div class="sect">
      <div class="sect-h">Duplicates merged into this story</div>
      ${d.duplicates.map(x=>`<div class="rel"><span>${esc(x.title)}</span></div>`).join('')}
    </div>` : ''}
    <div class="sect">
      <div class="sect-h">Source article</div>
      <a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.url)}</a>
      <details><summary>Show extracted text (${a.word_count} words)</summary>
        <pre>${esc(a.clean_text||'')}</pre></details>
    </div>
    <div class="sect">
      <div class="sect-h">Generate content</div>
      <div class="sect-btns">
        ${Object.keys(FMT).map(f=>`<button class="btn btn-sm" data-gen="${f}">${FMT[f]}</button>`).join('')}
        <button class="btn btn-sm btn-primary" data-gen="all">All formats</button>
      </div>
      <div id="drafts"></div>
    </div>`;

  $('#dr-body').querySelectorAll('[data-gen]').forEach(el=>{
    el.onclick = ()=>gen(el.dataset.gen, el);
  });

  const foot = COLS.map(c=>
    `<button class="btn btn-sm ${c.id===a.status?'btn-primary':''}" data-st="${c.id}">${c.label}</button>`).join('');
  $('#dr-foot').innerHTML = foot +
    `<button class="btn btn-sm btn-ghost" id="dr-copy" style="margin-left:auto">Copy latest draft</button>`;
  $('#dr-foot').querySelectorAll('[data-st]').forEach(el=>{
    el.onclick = ()=>{ move(id, el.dataset.st); open(id); };
  });
  $('#dr-copy').onclick = copyLatest;

  renderDrafts(d.drafts);
  $('#drawer').classList.add('on'); $('#scrim').classList.add('on');
}

function renderDrafts(drafts){
  const box = $('#drafts'); if(!box) return;
  if(!drafts || !drafts.length){ box.innerHTML = '<div class="empty">No drafts yet &mdash; pick a format above.</div>'; return; }
  box.innerHTML = drafts.map(d=>`
    <div class="draft">
      <div class="draft-h">
        <b>${FMT[d.draft_type]||d.draft_type}</b>
        <span class="tag">${esc(d.status)}</span>
        <span class="prov">${esc(d.provider||'')}</span>
      </div>
      <div class="draft-b">
        <textarea data-draft="${d.id}">${esc(d.human_edited_content ?? d.generated_content)}</textarea>
        <div style="display:flex;gap:6px;margin-top:6px">
          <button class="btn btn-sm" data-save="${d.id}">Save edit</button>
          <button class="btn btn-sm btn-ghost" data-copy="${d.id}">Copy</button>
        </div>
      </div>
    </div>`).join('');
  box.querySelectorAll('[data-save]').forEach(el=>{
    el.onclick = async ()=>{
      const ta = box.querySelector('textarea[data-draft="'+el.dataset.save+'"]');
      await api('/api/drafts/'+el.dataset.save, {method:'PATCH',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({human_edited_content:ta.value, status:'edited'})});
      toast('Draft saved'); loadStats();
    };
  });
  box.querySelectorAll('[data-copy]').forEach(el=>{
    el.onclick = ()=>{
      const ta = box.querySelector('textarea[data-draft="'+el.dataset.copy+'"]');
      navigator.clipboard.writeText(ta.value); toast('Copied to clipboard');
    };
  });
}

function copyLatest(){
  const tas = document.querySelectorAll('#drafts textarea');
  if(!tas.length) return toast('No drafts to copy');
  navigator.clipboard.writeText(tas[0].value); toast('Copied to clipboard');
}

async function gen(fmt, btn){
  const id = state.selected;
  const original = btn.innerHTML;
  btn.innerHTML = '<span class="spin"></span>'; btn.disabled = true;
  try{
    await api('/api/articles/'+id+'/generate', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify(fmt==='all' ? {all:true} : {format:fmt})});
    const d = await api('/api/articles/'+id);
    renderDrafts(d.drafts);
    toast(fmt==='all' ? 'Generated all formats' : 'Generated '+FMT[fmt]);
    loadStats();
  }catch(e){ toast('Generation failed: '+e.message); }
  finally{ btn.innerHTML = original; btn.disabled = false; }
}

function closeDrawer(){ $('#drawer').classList.remove('on'); $('#scrim').classList.remove('on'); state.selected=null; }

/* ---------------- ingestion ---------------- */
let polling;
async function runIngest(){
  const btn = $('#btn-ingest');
  btn.disabled = true; btn.innerHTML = '<span class="spin"></span> Ingesting&hellip;';
  try{
    await api('/api/ingest', {method:'POST'});
    toast('Ingestion started &mdash; fetching feeds&hellip;', 2500);
    polling = setInterval(pollJob, 1200);
  }catch(e){
    toast('Could not start: '+e.message);
    btn.disabled = false; btn.innerHTML = '&#8635; Run ingestion';
  }
}
async function pollJob(){
  const j = await api('/api/job');
  if(j.running) return;
  clearInterval(polling);
  const btn = $('#btn-ingest');
  btn.disabled = false; btn.innerHTML = '&#8635; Run ingestion';
  const s = j.stats || {};
  toast(`Done &mdash; <b>${s.new||0}</b> new, <b>${s.duplicates||0}</b> duplicates, ${s.sources_ok||0} feeds ok`
        + (s.errors && s.errors.length ? `, ${s.errors.length} feed errors` : ''), 5000);
  await Promise.all([loadStats(), loadArticles()]);
}

/* ================= SETTINGS ================= */
const INSTALL_HINTS = {
  crawl4ai: "pip install crawl4ai\ncrawl4ai-setup          # or: python -m playwright install chromium\npython -m playwright install-deps   # needs libnspr4, libnss3, libasound2",
  firecrawl: "no package needed\nexport FIRECRAWL_API_KEY=fc-...",
};

// Shown under the LLM provider selector so the panel tells you what to set.
const LLM_HINTS = {
  openai:     "export OPENAI_API_KEY=sk-...\nexport LLM_MODEL=gpt-4o-mini",
  openrouter: "export OPENROUTER_API_KEY=sk-or-...\nexport LLM_PROVIDER=openrouter\nexport LLM_MODEL=inclusionai/ling-3.0-flash-vl:free\n# OpenRouter is OpenAI-compatible: one key fronts many models.\n# ':free' ids are rate-limited but cost nothing.",
  ollama:     "ollama serve            # local, no key, no cost\nollama pull llama3.1",
};

async function loadSettings(){
  const d = await api('/api/settings');
  state.settings = d;
  renderBackendStatus(d);
  renderSettingsForm(d);
  $('#set-note').textContent = d.env_note;
  loadSourcesTable();
}

function renderBackendStatus(d){
  const f = d.fetcher, e = d.embedder;
  const llm = d.llm_enabled
    ? {k:'LLM', v:'enabled', s:'ok', d:'classification + generation via API'}
    : {k:'LLM', v:'heuristic', s:'warn', d:'no key - rules + templates, no cost'};
  const cards = [
    {k:'Full-text backend', v:f.backend, s:f.usable?'ok':'bad', d:f.detail},
    {k:'Embedder', v:e.backend, s:'ok', d:e.impl + ' · ' + e.dim + '-dim'},
    llm,
  ];
  $('#backend-status').innerHTML = cards.map(c=>`
    <div class="status-card">
      <div class="status-k">${esc(c.k)}</div>
      <div class="status-v"><span class="dotstate ${c.s}"></span>${esc(c.v)}</div>
      <div class="status-d">${esc(c.d)}</div>
    </div>`).join('');
}

function renderSettingsForm(d){
  const order = ['Full-text extraction','AI engine','Scoring','Pipeline'];
  const names = order.filter(g=>d.groups[g])
    .concat(Object.keys(d.groups).filter(g=>!order.includes(g)));
  $('#set-groups').innerHTML = names.map(g=>{
    const rows = d.groups[g].map(f=>{
      const hero = (f.key==='fetcher');
      let ctl;
      if(f.type==='choice'){
        ctl = '<select data-key="'+f.key+'">' +
          (f.choices||[]).map(c=>'<option value="'+esc(c)+'"'+
            (String(c)===String(f.value==null?'':f.value)?' selected':'')+'>'+esc(c||'(none)')+'</option>').join('') +
          '</select>';
      } else if(f.type==='bool'){
        ctl = '<label class="check"><input type="checkbox" data-key="'+f.key+'"'+(f.value?' checked':'')+'> '+(f.value?'on':'off')+'</label>';
      } else if(f.type==='json'){
        ctl = '<textarea data-key="'+f.key+'" spellcheck="false">'+esc(JSON.stringify(f.value||{},null,2))+'</textarea>';
      } else {
        const t = f.type==='secret' ? 'password'
                : (f.type==='float'||f.type==='int') ? 'number' : 'text';
        ctl = '<input type="'+t+'" data-key="'+f.key+'" value="'+esc(f.value==null?'':f.value)+'"'+
              (f.min!=null?' min="'+f.min+'"':'')+(f.max!=null?' max="'+f.max+'"':'')+
              (f.step!=null?' step="'+f.step+'"':'')+'>';
      }
      // one hint box per "which backend is active" selector
      const hintMap = f.key==='fetcher' ? INSTALL_HINTS
                   : f.key==='llm_provider' ? LLM_HINTS : null;
      const hint = (hintMap && hintMap[f.value])
        ? '<div class="install">'+esc(hintMap[f.value])+'</div>' : '';
      return '<div class="set-row'+(hero?' hero':'')+'">'+
        '<div><div class="set-lab">'+esc(f.label)+
          (f.overridden?'<span class="tag" style="color:var(--warn)">saved</span>':'')+'</div>'+
          (f.help?'<div class="set-help">'+esc(f.help)+'</div>':'')+'</div>'+
        '<div class="set-ctl">'+ctl+hint+'</div></div>';
    }).join('');
    return '<div class="set-group"><div class="set-group-h">'+esc(g)+'</div>'+
           '<div class="set-card">'+rows+'</div></div>';
  }).join('');

  // keep the hint boxes in sync with the selected backend / provider
  const syncHint = (key, map) => {
    $('#set-groups').querySelectorAll('select[data-key="'+key+'"]').forEach(sel=>{
      sel.onchange = ()=>{
        const row = sel.closest('.set-row');
        let box = row.querySelector('.install');
        const hint = map[sel.value];
        if(!hint){ if(box) box.remove(); return; }
        if(!box){
          box = document.createElement('div'); box.className='install';
          row.querySelector('.set-ctl').appendChild(box);
        }
        box.textContent = hint;
      };
    });
  };
  syncHint('fetcher', INSTALL_HINTS);
  syncHint('llm_provider', LLM_HINTS);
}

function collectSettings(){
  const out = {};
  $('#set-groups').querySelectorAll('[data-key]').forEach(el=>{
    const k = el.dataset.key;
    if(el.type==='checkbox') out[k] = el.checked;
    else if(el.tagName==='TEXTAREA'){
      try { out[k] = JSON.parse(el.value); } catch(e){ out[k] = el.value; }
    }
    else if(el.type==='number') out[k] = el.value===''?null:Number(el.value);
    else out[k] = el.value;
  });
  return out;
}

async function saveSettings(){
  const btn = $('#btn-save-settings');
  btn.disabled = true; btn.innerHTML = '<span class="spin"></span> Saving…';
  try{
    await api('/api/settings', {method:'PATCH',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify(collectSettings())});
    toast('Settings saved');
    await Promise.all([loadSettings(), loadStats()]);
  }catch(e){
    toast('Could not save — ' + (e.detail || e.message), 6000);
  }finally{
    btn.disabled = false; btn.innerHTML = 'Save changes';
  }
}

function switchView(v, updateHash){
  $('#board').hidden = v!=='board';
  $('#toolbar').hidden = v!=='board';
  $('#settings-view').hidden = v!=='settings';
  document.querySelectorAll('.navbtn').forEach(b=>b.classList.toggle('on', b.dataset.view===v));
  if(v==='settings') loadSettings();
  if(updateHash !== false){
    const h = v==='settings' ? '#settings' : '#board';
    if(location.hash !== h) history.replaceState(null, '', h);
  }
}

$('#nav').addEventListener('click', e=>{
  const b = e.target.closest('.navbtn'); if(b) switchView(b.dataset.view);
});
window.addEventListener('hashchange', ()=>{
  switchView(location.hash === '#settings' ? 'settings' : 'board', false);
});
$('#btn-save-settings').onclick = saveSettings;
$('#btn-reset-settings').onclick = async ()=>{
  if(!confirm('Drop every saved setting and return to the defaults from the environment?')) return;
  await api('/api/settings/reset', {method:'POST'});
  toast('Settings reset to defaults');
  await Promise.all([loadSettings(), loadStats()]);
};

/* ================= SOURCES ================= */
async function loadSourcesTable(){
  const d = await api('/api/sources');
  state.sources = d.items;
  renderSourcesTable();
}

function renderSourcesTable(){
  const catSel = $('#src-cat');
  if(catSel.options.length===0){
    const cats = (state.stats && state.stats.categories || []).map(c=>c.category);
    const all = [...new Set(['general-dev'].concat(cats))];
    catSel.innerHTML = all.map(c=>'<option value="'+esc(c)+'">'+esc(c)+'</option>').join('');
  }

  const rows = state.sources.map(s=>{
    const h = s.last_status==='ok' ? 'ok' : s.last_status==='error' ? 'err' : 'never';
    const hLabel = h==='ok' ? (s.items_last_fetch+' entries')
                  : h==='err' ? 'error' : 'not fetched';
    return '<div class="src-row'+(s.is_active?'':' off')+'" data-src="'+s.id+'">'+
      '<div><div class="src-name">'+esc(s.name)+
        (s.managed?'<span class="src-badge">yours</span>':'')+'</div>'+
        '<div class="src-meta">'+esc(s.feed_url)+'</div></div>'+
      '<div class="src-stats">'+
        '<span class="src-health '+(h==='ok'?'ok':h==='err'?'err':'never')+'" title="'+
          esc(s.last_error||'')+'">'+hLabel+'</span>'+
        '<span>'+s.articles+' articles</span>'+
        '<span>auth '+s.authority+'</span></div>'+
      '<span class="cat">'+esc(s.category)+'</span>'+
      '<div class="src-act">'+
        '<button class="xbtn" data-toggle="'+s.id+'" title="'+(s.is_active?'Disable':'Enable')+'">'+
          (s.is_active?'on':'off')+'</button>'+
        '<button class="xbtn" data-del="'+s.id+'" title="Remove">&#10005;</button>'+
      '</div></div>';
  }).join('');
  $('#src-list').innerHTML = rows || '<div class="src-empty">No sources yet.</div>';

  $('#src-list').querySelectorAll('[data-toggle]').forEach(b=>{
    b.onclick = async ()=>{
      const s = state.sources.find(x=>String(x.id)===b.dataset.toggle);
      await api('/api/sources/'+b.dataset.toggle, {method:'PATCH',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({is_active: !s.is_active})});
      toast(s.is_active ? 'Feed disabled' : 'Feed enabled');
      await Promise.all([loadSourcesTable(), loadStats()]);
    };
  });
  $('#src-list').querySelectorAll('[data-del]').forEach(b=>{
    b.onclick = async ()=>{
      const s = state.sources.find(x=>String(x.id)===b.dataset.del);
      if(!confirm('Remove "'+s.name+'"? Its '+s.articles+' existing articles are kept.')) return;
      await api('/api/sources/'+b.dataset.del, {method:'DELETE'});
      toast('Feed removed');
      await Promise.all([loadSourcesTable(), loadStats()]);
    };
  });
}

$('#btn-add-source').onclick = async ()=>{
  const name = $('#src-name').value.trim();
  const url  = $('#src-url').value.trim();
  if(!name || !url) return toast('Give the feed a name and a URL');
  if(!/^https?:\/\//.test(url)) return toast('URL must start with http:// or https://');
  const btn = $('#btn-add-source');
  btn.disabled = true; btn.innerHTML = '<span class="spin"></span>';
  try{
    await api('/api/sources', {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({name, feed_url:url, category:$('#src-cat').value,
                           authority:Number($('#src-auth').value)||0.7})});
    $('#src-name').value = ''; $('#src-url').value = '';
    toast('Feed added — fetching now');
    await Promise.all([loadSourcesTable(), loadStats()]);
  }catch(e){ toast('Could not add: ' + (e.detail||e.message)); }
  finally{ btn.disabled = false; btn.innerHTML = 'Add feed'; }
};

/* ---------------- wiring ---------------- */
$('#btn-ingest').onclick = runIngest;
$('#dr-close').onclick = closeDrawer;
$('#scrim').onclick = closeDrawer;
document.addEventListener('keydown', e=>{ if(e.key==='Escape') closeDrawer(); });

let searchT;
$('#search').oninput = e=>{
  clearTimeout(searchT);
  searchT = setTimeout(()=>{ state.q = e.target.value.trim(); loadArticles(); }, 260);
};
$('#f-source').onchange = e=>{ state.source = e.target.value; loadArticles(); };
$('#f-diff').onchange = e=>{ state.difficulty = e.target.value; loadArticles(); };
$('#f-sort').onchange = e=>{ state.sort = e.target.value; loadArticles(); };
$('#f-dupes').onchange = e=>{ state.dupes = e.target.checked; loadArticles(); };

/* status tabs live in the board header clicks? use pills instead */
$('#pills').addEventListener('click', e=>{
  const p = e.target.closest('.pill'); if(!p) return;
  const txt = p.textContent.trim().split(' ')[0];
  state.status = (state.status === txt) ? 'all' : txt;
  loadArticles();
});

/* ---------------- theme ---------------- */
const THEME_KEY = 'tc-theme';

function currentTheme(){
  return document.documentElement.dataset.theme
      || (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
}

function applyTheme(t){
  document.documentElement.dataset.theme = t;
  const lbl = $('#theme-label');
  if(lbl) lbl.textContent = t === 'light' ? 'Light' : 'Dark';
  const btn = $('#btn-theme');
  if(btn) btn.title = t === 'light' ? 'Switch to dark theme' : 'Switch to light theme';
  const meta = document.querySelector('meta[name="theme-color"]');
  if(meta) meta.content = t === 'light' ? '#f4f6fa' : '#0a0e14';
}

function initTheme(){
  let stored = null;
  try { stored = localStorage.getItem(THEME_KEY); } catch(e){}
  applyTheme(stored === 'light' || stored === 'dark' ? stored : currentTheme());
}

$('#btn-theme').onclick = ()=>{
  const next = currentTheme() === 'light' ? 'dark' : 'light';
  applyTheme(next);
  try { localStorage.setItem(THEME_KEY, next); } catch(e){}
};

// follow the OS while the user has not made an explicit choice
matchMedia('(prefers-color-scheme: light)').addEventListener('change', e=>{
  let stored = null;
  try { stored = localStorage.getItem(THEME_KEY); } catch(e){}
  if(!stored) applyTheme(e.matches ? 'light' : 'dark');
});

/* ---------------- boot ---------------- */
(async function(){
  initTheme();
  await loadStats();
  await loadArticles();
  // honour #settings on load so a refresh keeps you on the tab you were on
  switchView(location.hash === '#settings' ? 'settings' : 'board', false);
  setInterval(loadStats, 20000);
})();
</script>
</body>
</html>
"""
