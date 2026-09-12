NAV_HTML = """
<style>
    .bird-nav { background: #2c3e50; padding: 12px 20px; margin-bottom: 20px; border-radius: 8px; display: flex; gap: 20px; align-items: center; flex-wrap: wrap; }
    .bird-nav a { color: #ecf0f1; text-decoration: none; font-weight: 600; font-size: 14px; padding: 6px 12px; border-radius: 4px; transition: background 0.2s; }
    .bird-nav a:hover { background: rgba(255,255,255,0.15); }
    .bird-nav a.active { background: #007bff; }
    .bird-nav .brand { font-size: 16px; margin-right: 10px; }
</style>
<div class="bird-nav">
    <span class="brand">🐦</span>
    <a href="/manage" id="nav-manage">Manage</a>
    <a href="/gallery" id="nav-gallery">Gallery</a>
    <a href="/species-queue" id="nav-species-queue">Species Queue</a>
    <a href="/trash" id="nav-trash">Trash</a>
    <a href="/api/stats" id="nav-stats">Stats</a>
</div>
<script>
    (function() {
        const path = window.location.pathname;
        const map = { '/gallery': 'nav-gallery', '/manage': 'nav-manage', '/trash': 'nav-trash', '/species-queue': 'nav-species-queue' };
        const id = map[path];
        if (id) document.getElementById(id).classList.add('active');
    })();
</script>
"""
