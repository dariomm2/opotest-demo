from __future__ import annotations

import argparse
import shutil
from pathlib import Path

DEFAULT_BASE_PATH = "/optest"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: esperaba 1 coincidencia y encontré {count}.")
    return text.replace(old, new, 1)


def sanitize_legacy_references(repo: Path) -> None:
    """Retira del código copiado cualquier nombre histórico de la app base."""
    legacy_display = "Bomb" + "AvTest"
    legacy_lower = "bomba" + "vtest"
    legacy_upper = legacy_lower.upper()
    legacy_split = "Bomb" + "Av<span>Test</span>"
    replacements = (
        (legacy_upper, "OPTEST"),
        (legacy_display, "OpoTest"),
        (legacy_lower, "optest"),
        (legacy_split, "Opo<span>Test</span>"),
    )
    for path in repo.rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        updated = text
        for old, new in replacements:
            updated = updated.replace(old, new)
        if updated != text:
            path.write_text(updated, encoding="utf-8")


def assert_no_legacy_references(repo: Path) -> None:
    legacy_tokens = ("Bomb" + "AvTest", "bomba" + "vtest")
    for path in repo.rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        lowered = text.lower()
        for token in legacy_tokens:
            if token.lower() in lowered:
                raise RuntimeError(f"Referencia histórica encontrada todavía en {path}")


def patch_auth(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "from .db import bind_db, connect_db, get_db, reset_db\n",
        "from .db import bind_db, connect_db, get_db, reset_db\n"
        "from .demo_runtime import (\n"
        "    cleanup_demo_session, demo_connection_for_request, demo_cookie_path,\n"
        "    demo_mode_enabled,\n"
        ")\n",
        "auth import demo_runtime",
    )
    text = replace_once(
        text,
        "            db = connect_db()\n            db_token = bind_db(db)\n",
        "            db = demo_connection_for_request(http_request) if demo_mode_enabled() else connect_db()\n"
        "            db_token = bind_db(db)\n",
        "auth request DB",
    )

    demo_login = '''@router.post("/api/demo-login")
def demo_login():
    if not demo_mode_enabled():
        return api_error("Ruta no disponible.", 404, "NOT_FOUND")

    data = json_body() or {}
    requested_role = str(data.get("role", "")).strip().lower()
    role = "admin" if requested_role == "admin" else "user" if requested_role in {"user", "student", "alumno"} else None
    if role is None:
        return api_error("Selecciona un perfil de demo válido.", 400, "INVALID_DEMO_ROLE")

    preferred_env = "OPTEST_DEMO_ADMIN_USERNAME" if role == "admin" else "OPTEST_DEMO_STUDENT_USERNAME"
    preferred_username = os.environ.get(preferred_env, "").strip()
    db = get_db()
    account = None
    if preferred_username:
        account = db.execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE AND role = ? AND is_active = 1",
            (preferred_username, role),
        ).fetchone()
    if account is None:
        account = db.execute(
            "SELECT * FROM users WHERE role = ? AND is_active = 1 ORDER BY id LIMIT 1",
            (role,),
        ).fetchone()
    if account is None:
        label = "administrador" if role == "admin" else "alumno"
        return api_error(f"La base de datos de demo no contiene ningún {label} activo.", 503, "DEMO_ACCOUNT_MISSING")

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    csrf_token = secrets.token_urlsafe(24)
    created = utc_now()
    expires = created + timedelta(days=SESSION_DAYS)
    db.execute("DELETE FROM sessions WHERE expires_at <= ?", (utc_iso(created),))
    db.execute(
        "INSERT INTO sessions(user_id, token_hash, csrf_token, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
        (account["id"], token_hash, csrf_token, utc_iso(expires), utc_iso(created)),
    )
    db.commit()

    response = make_response(jsonify({
        "ok": True,
        "data": {
            "user": {
                "id": int(account["id"]), "username": account["username"],
                "display_name": account["display_name"], "role": account["role"],
            },
            "csrf_token": csrf_token,
        },
    }))
    response.set_cookie(
        SESSION_COOKIE, raw_token, max_age=SESSION_DAYS * 24 * 60 * 60,
        httponly=True, samesite="Lax", secure=secure_cookie_request(), path=demo_cookie_path(),
    )
    return response

'''
    text = replace_once(
        text,
        '@router.post("/api/login")\n',
        demo_login + '@router.post("/api/login")\n',
        "demo role login endpoint",
    )
    text = replace_once(
        text,
        '        httponly=True, samesite="Lax", secure=secure_cookie_request(), path="/",\n',
        '        httponly=True, samesite="Lax", secure=secure_cookie_request(), path=demo_cookie_path(),\n',
        "login cookie path",
    )
    text = replace_once(
        text,
        '    response.delete_cookie(SESSION_COOKIE, path="/")\n',
        "    if demo_mode_enabled():\n"
        "        cleanup_demo_session(raw_token)\n"
        "    response.delete_cookie(SESSION_COOKIE, path=demo_cookie_path())\n",
        "logout cleanup",
    )
    path.write_text(text, encoding="utf-8")


def patch_admin(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "    MAX_TOPIC_ATTACHMENTS_BYTES,\n)",
        "    MAX_TOPIC_ATTACHMENTS_BYTES,\n    SESSION_COOKIE,\n)",
        "admin SESSION_COOKIE import",
    )
    text = replace_once(
        text,
        "from .db import get_db\n",
        "from .db import get_db\n"
        "from .demo_runtime import (\n"
        "    demo_mode_enabled, demo_storage_delete, demo_storage_put, demo_storage_response,\n"
        ")\n",
        "admin demo_runtime import",
    )
    text = replace_once(
        text,
        "def storage_put(file_storage: UploadFile, key: str, mime_type: str) -> None:\n    try:\n",
        "def storage_put(file_storage: UploadFile, key: str, mime_type: str) -> None:\n"
        "    if demo_mode_enabled():\n"
        "        demo_storage_put(request.cookies.get(SESSION_COOKIE, \"\"), file_storage, key)\n"
        "        return\n"
        "    try:\n",
        "admin storage_put",
    )
    text = replace_once(
        text,
        "def storage_delete(key: str) -> None:\n    try:\n",
        "def storage_delete(key: str) -> None:\n"
        "    if demo_mode_enabled():\n"
        "        demo_storage_delete(request.cookies.get(SESSION_COOKIE, \"\"), key)\n"
        "        return\n"
        "    try:\n",
        "admin storage_delete",
    )
    text = replace_once(
        text,
        "def storage_response(key: str, filename: str, mime_type: str):\n    try:\n",
        "def storage_response(key: str, filename: str, mime_type: str):\n"
        "    if demo_mode_enabled():\n"
        "        demo_response = demo_storage_response(\n"
        "            request.cookies.get(SESSION_COOKIE, \"\"), key, filename, mime_type\n"
        "        )\n"
        "        if demo_response is not None:\n"
        "            return demo_response\n"
        "    try:\n",
        "admin storage_response",
    )
    path.write_text(text, encoding="utf-8")


def patch_frontend_script(path: Path, base_path: str) -> None:
    text = path.read_text(encoding="utf-8")

    # First adapt original pathname reads, before inserting helpers that themselves use location.pathname.
    count_pathname = text.count("location.pathname")
    if count_pathname < 3:
        raise RuntimeError(f"frontend pathname: esperaba >=3 coincidencias y encontré {count_pathname}.")
    text = text.replace("location.pathname", "optestLogicalPath(location.pathname)")

    marker = "'use strict';\n" if "'use strict';\n" in text else None
    helper = f'''\nconst OPTEST_BASE_PATH = {base_path!r};\n\nfunction optestUrl(path) {{\n  if (typeof path !== 'string' || !path.startsWith('/')) return path;\n  if (!OPTEST_BASE_PATH || OPTEST_BASE_PATH === '/') return path;\n  if (path === OPTEST_BASE_PATH || path.startsWith(`${{OPTEST_BASE_PATH}}/`)) return path;\n  return `${{OPTEST_BASE_PATH}}${{path}}`;\n}}\n\nfunction optestLogicalPath(path) {{\n  if (typeof path !== 'string') return path;\n  if (!OPTEST_BASE_PATH || OPTEST_BASE_PATH === '/') return path;\n  if (path === OPTEST_BASE_PATH || path === `${{OPTEST_BASE_PATH}}/`) return '/';\n  if (path.startsWith(`${{OPTEST_BASE_PATH}}/`)) return path.slice(OPTEST_BASE_PATH.length) || '/';\n  return path;\n}}\n\nconst optestPushState = history.pushState.bind(history);\nhistory.pushState = (state, title, url) =>\n  optestPushState(state, title, typeof url === 'string' ? optestUrl(url) : url);\nconst optestReplaceState = history.replaceState.bind(history);\nhistory.replaceState = (state, title, url) =>\n  optestReplaceState(state, title, typeof url === 'string' ? optestUrl(url) : url);\n'''
    if marker:
        text = replace_once(text, marker, marker + helper, "frontend helper insertion")
    else:
        text = helper + "\n" + text

    text = replace_once(
        text,
        "response = await fetch(path, requestOptions);",
        "response = await fetch(optestUrl(path), requestOptions);",
        "frontend api fetch",
    )
    text = replace_once(
        text,
        "response = await fetch(path, { method, headers, body: formData, credentials: 'same-origin' });",
        "response = await fetch(optestUrl(path), { method, headers, body: formData, credentials: 'same-origin' });",
        "frontend form fetch",
    )

    # Attachment URLs come from the backend as root-relative /api/... paths.
    text = text.replace("escapeHtml(file.download_url)", "escapeHtml(optestUrl(file.download_url))")
    text = text.replace("escapeHtml(downloadUrl)", "escapeHtml(optestUrl(downloadUrl))")

    text = replace_once(
        text,
        'function applyTheme(theme) {\n  const dark = theme === \'dark\';\n  document.documentElement.dataset.theme = dark ? \'dark\' : \'light\';\n  byId(\'themeToggle\').setAttribute(\'aria-label\', dark ? \'Activar modo claro\' : \'Activar modo oscuro\');\n  document.querySelector(\'meta[name="theme-color"]\').setAttribute(\'content\', dark ? \'#0d1517\' : \'#0f766e\');\n}\n',
        'function applyTheme(theme) {\n  const dark = theme === \'dark\';\n  document.documentElement.dataset.theme = dark ? \'dark\' : \'light\';\n  [byId(\'themeToggle\'), byId(\'demoLoginThemeToggle\')].filter(Boolean).forEach(button => {\n    button.setAttribute(\'aria-label\', dark ? \'Activar modo claro\' : \'Activar modo oscuro\');\n  });\n  document.querySelector(\'meta[name="theme-color"]\').setAttribute(\'content\', dark ? \'#0d1517\' : \'#0f766e\');\n}\n',
        "demo dual theme toggle",
    )

    old_reset_stats = '''function resetStatsWorkspace() {
  state.statsScope.mode = 'self';
  state.statsScope.userId = null;
  state.statsScope.search = '';
  const search = byId('statsUserSearch');
  if (search) search.value = '';
  document.querySelectorAll('[data-stats-scope]').forEach(button => {
    button.classList.toggle('active', button.dataset.statsScope === 'self');
  });
}
'''
    new_reset_stats = '''function resetStatsWorkspace() {
  state.statsScope.mode = state.user?.role === 'admin' ? 'all' : 'self';
  state.statsScope.userId = null;
  state.statsScope.search = '';
  const search = byId('statsUserSearch');
  if (search) search.value = '';
  document.querySelectorAll('[data-stats-scope]').forEach(button => {
    button.classList.toggle('active', button.dataset.statsScope === state.statsScope.mode);
  });
}
'''
    text = replace_once(text, old_reset_stats, new_reset_stats, "demo stats default scope")

    old_role_ui = '''function updateRoleUI() {
  const isAdmin = state.user?.role === 'admin';
  byId('adminNavBtn').hidden = !isAdmin;
  document.querySelector('.nav-center')?.classList.toggle('has-admin', isAdmin);
  const statsTabs = byId('statsScopeTabs');
  if (statsTabs) statsTabs.hidden = !isAdmin;
  if (!isAdmin) {
    state.statsScope.mode = 'self';
    state.statsScope.userId = null;
  }
}
'''
    new_role_ui = '''function updateRoleUI() {
  const isAdmin = state.user?.role === 'admin';
  const homeNav = byId('studentHomeNavBtn');
  if (homeNav) homeNav.hidden = isAdmin;
  byId('adminNavBtn').hidden = !isAdmin;
  document.querySelector('.nav-center')?.classList.remove('has-admin');
  const questionMode = byId('questionModeControl');
  if (questionMode) questionMode.hidden = isAdmin;
  const statsTabs = byId('statsScopeTabs');
  if (statsTabs) statsTabs.hidden = !isAdmin;
  byId('topbar')?.classList.toggle('demo-admin-mode', isAdmin);
  byId('appShell')?.classList.toggle('demo-admin-shell', isAdmin);
  if (isAdmin) {
    if (state.statsScope.mode === 'self') state.statsScope.mode = 'all';
    state.statsScope.userId = state.statsScope.mode === 'student' ? state.statsScope.userId : null;
  } else {
    state.statsScope.mode = 'self';
    state.statsScope.userId = null;
  }
}
'''
    text = replace_once(text, old_role_ui, new_role_ui, "demo role UI")

    demo_handler = '''async function handleDemoRoleLogin(role, button) {
  const errorNode = byId('loginError');
  errorNode.textContent = '';
  const roleButtons = [...document.querySelectorAll('[data-demo-role]')];
  roleButtons.forEach(node => { node.disabled = true; });
  if (button) button.classList.add('is-loading');
  try {
    const data = await api('/api/demo-login', { method: 'POST', body: { role } });
    state.user = data.user;
    state.csrf = data.csrf_token;
    state.home = null;
    state.stats = null;
    state.statsScope = { mode: data.user.role === 'admin' ? 'all' : 'self', userId: null, users: null, search: '' };
    showApp();
    await setView(data.user.role === 'admin' ? 'admin' : 'home', true);
  } catch (error) {
    errorNode.textContent = error.message;
  } finally {
    roleButtons.forEach(node => { node.disabled = false; });
    if (button) button.classList.remove('is-loading');
  }
}

'''
    text = replace_once(
        text,
        "async function handleLogin(event) {\n",
        demo_handler + "async function handleLogin(event) {\n",
        "demo role handler",
    )

    old_set_view_guard = '''  if (view === 'question' && !state.session) view = 'home';
  if (view === 'review' && !state.examReview) view = 'home';
  if (view === 'admin' && state.user.role !== 'admin') {
    showToast('No tienes permisos de administrador.');
    if (!push && optestLogicalPath(location.pathname) === '/admin') history.replaceState({}, '', '/');
    view = 'home';
  }
'''
    new_set_view_guard = '''  const isAdmin = state.user.role === 'admin';
  if (isAdmin && ['home', 'question', 'review'].includes(view)) view = 'admin';
  if (!isAdmin && view === 'question' && !state.session) view = 'home';
  if (!isAdmin && view === 'review' && !state.examReview) view = 'home';
  if (!isAdmin && view === 'admin') {
    showToast('No tienes permisos de administrador.');
    if (!push && optestLogicalPath(location.pathname) === '/admin') history.replaceState({}, '', '/');
    view = 'home';
  }
'''
    text = replace_once(text, old_set_view_guard, new_set_view_guard, "demo navigation permissions")

    text = replace_once(
        text,
        "  byId('logoutBtn').addEventListener('click', handleLogout);\n",
        "  byId('logoutBtn').addEventListener('click', handleLogout);\n"
        "  byId('changeUserBtn').addEventListener('click', handleLogout);\n"
        "  byId('demoLoginThemeToggle')?.addEventListener('click', () => {\n"
        "    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';\n"
        "    safeStorageSet('opotest-theme', next);\n"
        "    applyTheme(next);\n"
        "  });\n"
        "  document.querySelectorAll('[data-demo-role]').forEach(button => {\n"
        "    button.addEventListener('click', () => handleDemoRoleLogin(button.dataset.demoRole, button));\n"
        "  });\n",
        "demo role events",
    )

    # Admins never get the private 'self' scope in the demo, even through manually-dispatched DOM events.
    text = replace_once(
        text,
        "async function setStatsScope(mode) {\n  if (!['self', 'student', 'all'].includes(mode)) return;\n",
        "async function setStatsScope(mode) {\n"
        "  if (!['self', 'student', 'all'].includes(mode)) return;\n"
        "  if (state.user?.role === 'admin' && mode === 'self') mode = 'all';\n"
        "  if (state.user?.role !== 'admin') mode = 'self';\n",
        "demo stats scope permissions",
    )

    path.write_text(text, encoding="utf-8")


def patch_frontend_html(path: Path, base_path: str) -> None:
    text = path.read_text(encoding="utf-8")
    prefix = base_path.rstrip("/")

    login_start = text.index('  <section class="login-shell" id="loginView" hidden>')
    login_end = text.index('  <div class="app-shell" id="appShell" hidden>')
    demo_login = '''  <section class="login-shell demo-role-shell" id="loginView" hidden>
    <header class="demo-login-topbar" aria-label="Cabecera de OpoTest Demo">
      <div class="brand" aria-label="OpoTest"><span class="brand-name">Opo<span>Test</span></span></div>
      <button class="theme-toggle" id="demoLoginThemeToggle" type="button" aria-label="Activar modo oscuro" title="Cambiar tema">
        <svg class="sun-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="4" stroke="currentColor" stroke-width="2"/><path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.66 6.34l1.41-1.41" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
        <svg class="moon-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M20.5 15.2A8.4 8.4 0 0 1 8.8 3.5 8.5 8.5 0 1 0 20.5 15.2Z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>
      </button>
    </header>
    <div class="login-card demo-role-card">
      <h1>Explora la demo</h1>
      <p class="demo-role-copy">Elige el perfil con el que quieres entrar.</p>
      <div class="demo-role-actions" aria-label="Seleccionar perfil de demo">
        <button class="demo-role-button" type="button" data-demo-role="user">
          <span class="demo-role-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="8" r="3.2" stroke="currentColor" stroke-width="1.8"/><path d="M5.5 20c.5-4 2.8-6 6.5-6s6 2 6.5 6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
          </span>
          <span><strong>Alumno</strong><small>Práctica, simulacros y tus estadísticas</small></span>
        </button>
        <button class="demo-role-button" type="button" data-demo-role="admin">
          <span class="demo-role-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none"><path d="M12 3 4.8 6v5.1c0 4.4 3 7.3 7.2 9.4 4.2-2.1 7.2-5 7.2-9.4V6L12 3Z" stroke="currentColor" stroke-width="1.8"/><path d="M9.6 12.1 11 13.5l3.5-3.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </span>
          <span><strong>Administrador</strong><small>Gestión y estadísticas de alumnos</small></span>
        </button>
      </div>
      <div class="form-error demo-role-error" id="loginError" role="alert"></div>
      <form id="loginForm" hidden aria-hidden="true">
        <input id="loginUsername" tabindex="-1">
        <input id="loginPassword" type="password" tabindex="-1">
        <button id="loginPasswordToggle" type="button" tabindex="-1"></button>
        <button id="loginSubmit" type="submit" tabindex="-1"></button>
      </form>
    </div>
  </section>
'''
    text = text[:login_start] + demo_login + text[login_end:]

    text = replace_once(text, "<title>OpoTest</title>", "<title>OpoTest Demo</title>", "demo title")
    text = replace_once(
        text,
        '''      <a class="brand" href="/" data-nav="home" aria-label="Ir al inicio">
        <span class="brand-name">Opo<span>Test</span></span>
      </a>
''',
        '''      <div class="demo-brand-cluster">
        <a class="brand" href="/" data-nav="home" aria-label="Ir al inicio">
          <span class="brand-name">Opo<span>Test</span></span>
        </a>
        <button class="demo-change-user" id="changeUserBtn" type="button" aria-label="Cambiar de perfil">
          <svg class="demo-change-user-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m15 18-6-6 6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
          <span>Cambio de usuario</span>
        </button>
      </div>
''',
        "demo navbar brand",
    )
    text = replace_once(
        text,
        '<button class="nav-link active" type="button" data-nav="home">',
        '<button class="nav-link active" id="studentHomeNavBtn" type="button" data-nav="home">',
        "student home nav id",
    )
    text = replace_once(
        text,
        '          <button class="admin-tab active" type="button" data-stats-scope="self">Mis estadísticas</button>\n',
        "",
        "remove admin self stats tab",
    )
    text = replace_once(
        text,
        '<button class="admin-tab" type="button" data-stats-scope="all">Todos los alumnos</button>',
        '<button class="admin-tab active" type="button" data-stats-scope="all">Todos los alumnos</button>',
        "admin all stats default tab",
    )

    replacements = {
        'href="/styles.css"': f'href="{prefix}/styles.css"',
        'href="/" data-nav="home"': f'href="{prefix}/" data-nav="home"',
        'src="/version.js"': f'src="{prefix}/version.js"',
        'src="/script.js"': f'src="{prefix}/script.js"',
    }
    for old, new in replacements.items():
        text = replace_once(text, old, new, f"frontend HTML {old}")

    # La demo pública no expone ni reutiliza los datos personales del aviso legal de producción.
    legal_replacements = {
        '<div class="legal-brand" aria-label="OpoTest">Opo<span>Test</span></div>':
            '<div class="legal-brand" aria-label="OpoTest Demo">Opo<span>Test</span> Demo</div>',
        '<p><strong>Titular:</strong> Ricardo Magariño Manteca<br><strong>NIF:</strong> 51095882W<br><strong>Domicilio:</strong> Avenida de la Constitución 4, 05194 Mediana de Voltoya, Ávila, España<br><strong>Correo electrónico:</strong> rikimdv@gmail.com</p>':
            '<p><strong>Versión:</strong> OpoTest Demo<br><strong>Datos identificativos:</strong> omitidos en esta demostración pública.</p><p class="legal-demo-note"><strong>Nota:</strong> esta versión utiliza exclusivamente cuentas, nombres, preguntas y actividad sintéticos. Las acciones realizadas por el visitante se guardan únicamente en una copia temporal aislada y no modifican la plantilla común.</p>',
        '<p>Para cualquier consulta relacionada con OpoTest o con el titular del servicio puede utilizarse el correo electrónico <strong>rikimdv@gmail.com</strong>.</p>':
            '<p>Esta página forma parte de una demostración técnica y no publica datos personales de contacto del servicio de producción.</p>',
        '<p><strong>Responsable:</strong> Ricardo Magariño Manteca<br><strong>NIF:</strong> 51095882W<br><strong>Domicilio:</strong> Avenida de la Constitución 4, 05194 Mediana de Voltoya, Ávila, España<br><strong>Correo electrónico:</strong> rikimdv@gmail.com</p>':
            '<p><strong>Versión:</strong> OpoTest Demo<br><strong>Datos personales reales:</strong> no se incluyen en el dataset de demostración.</p><p class="legal-demo-note">Los perfiles, nombres de alumnos, respuestas y estadísticas mostrados son sintéticos. Los cambios del visitante viven únicamente durante su sesión aislada.</p>',
        '<li>Nombre y apellidos y nombre de usuario.</li>':
            '<li>Nombres y usuarios ficticios incluidos únicamente como datos sintéticos de demostración.</li>',
        '<li>Credenciales de acceso, almacenando la contraseña mediante un mecanismo criptográfico y no en texto plano.</li>':
            '<li>Selección temporal del perfil Alumno o Administrador; la demo pública no solicita credenciales personales.</li>',
        '<p>El usuario puede ejercer, cuando corresponda, sus derechos de acceso, rectificación, supresión, limitación, oposición y portabilidad dirigiéndose a <strong>rikimdv@gmail.com</strong> o por escrito a <strong>Avenida de la Constitución 4, 05194 Mediana de Voltoya, Ávila, España</strong>.</p>':
            '<p>La demo no solicita datos identificativos del visitante ni crea cuentas personales persistentes. Cualquier dato introducido durante la sesión se almacena solo en una copia temporal aislada que se elimina al cambiar de usuario, cerrar sesión o caducar.</p>',
        '<p><strong>Última actualización:</strong> 27 de agosto de 2026.</p>':
            '<p><strong>Última actualización de la demo:</strong> 10 de septiembre de 2026.</p>',
    }
    for old, new in legal_replacements.items():
        text = replace_once(text, old, new, f"demo legal {old[:36]}")
    path.write_text(text, encoding="utf-8")


def patch_frontend_styles(path: Path, base_path: str = DEFAULT_BASE_PATH) -> None:
    text = path.read_text(encoding="utf-8")
    prefix = "/" + base_path.strip("/") if base_path.strip("/") else ""
    icon_prefix = f"{prefix}/assets/icons/" if prefix else "/assets/icons/"
    text = text.replace("url('/assets/icons/", f"url('{icon_prefix}")
    styles = r'''

/* --------------------------------------------------------------------------
   OpoTest public demo: role chooser and split navigation
   -------------------------------------------------------------------------- */
.demo-login-topbar {
  position: fixed;
  inset: 0 0 auto 0;
  z-index: 80;
  height: 64px;
  padding: 0 clamp(18px, 4vw, 42px);
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--line);
  background: color-mix(in srgb, var(--bg) 92%, transparent);
  backdrop-filter: blur(14px);
}
.demo-login-topbar .brand { pointer-events: none; }
.demo-role-shell { padding-top: 64px; }
.demo-role-card { width: min(520px, 100%); }
.demo-role-card .login-brand { margin-bottom: 30px; }
.demo-role-card h1 { margin-bottom: 8px; }
.demo-role-copy {
  margin: 0 0 24px;
  color: var(--muted);
  font-size: .9rem;
  line-height: 1.5;
}
.demo-role-actions { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.demo-role-button {
  min-width: 0;
  min-height: 132px;
  display: grid;
  grid-template-rows: auto 1fr;
  align-content: start;
  gap: 14px;
  padding: 18px;
  border: 1px solid var(--line);
  border-radius: 16px;
  color: var(--text);
  background: var(--surface-soft);
  text-align: left;
  transition: transform .16s ease, border-color .16s ease, background-color .16s ease, box-shadow .16s ease;
}
.demo-role-button:hover:not(:disabled) {
  transform: translateY(-2px);
  border-color: color-mix(in srgb, var(--brand) 46%, var(--line));
  background: var(--surface);
  box-shadow: var(--shadow-sm);
}
.demo-role-button:disabled { cursor: wait; opacity: .62; }
.demo-role-button > span:last-child { display: grid; gap: 5px; }
.demo-role-button strong { font-size: .92rem; }
.demo-role-button small { color: var(--muted); font-size: .72rem; line-height: 1.4; font-weight: 650; }
.demo-role-icon {
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border-radius: 11px;
  color: var(--brand-strong);
  background: var(--brand-soft);
}
.demo-role-icon svg { width: 21px; height: 21px; }
.demo-role-error { margin-top: 14px; }

.topbar { grid-template-areas: "brand nav switch theme"; }
.demo-brand-cluster {
  grid-area: brand;
  min-width: max-content;
  display: inline-flex;
  align-items: center;
  justify-self: start;
  gap: 12px;
}
.nav-center { grid-area: nav; }
.question-switch { grid-area: switch; }
.theme-toggle { grid-area: theme; }
.demo-change-user {
  min-height: 30px;
  padding: 0 9px;
  border: 1px solid var(--line);
  border-radius: 9px;
  color: var(--muted);
  background: var(--surface-soft);
  font-size: .7rem;
  font-weight: 760;
  white-space: nowrap;
  transition: color .16s ease, border-color .16s ease, background-color .16s ease;
}
.demo-change-user:hover { color: var(--text); border-color: var(--brand); background: var(--brand-soft); }
.hero-logout { display: none !important; }
.hero-copy { padding-right: 0 !important; }

@media (max-width: 720px) {
  .demo-role-card { padding: 24px 20px; }
  .demo-role-actions { grid-template-columns: 1fr; }
  .demo-role-button { min-height: 94px; grid-template-columns: auto 1fr; grid-template-rows: none; align-items: center; }

  .app-shell { padding-top: 112px; }
  .topbar {
    height: 112px;
    min-height: 112px;
    grid-template-columns: minmax(0, 1fr) auto;
    grid-template-areas:
      "brand theme"
      "nav nav"
      "switch switch";
    row-gap: 5px;
  }
  .demo-brand-cluster { min-width: 0; max-width: calc(100vw - 64px); gap: 8px; }
  .brand-name { font-size: .98rem; }
  .demo-change-user { min-height: 27px; padding-inline: 7px; font-size: .62rem; overflow: hidden; text-overflow: ellipsis; }
  .nav-center,
  .nav-center.has-admin { width: 100%; max-width: none; grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .question-switch { justify-self: stretch; }

  .app-shell.demo-admin-shell { padding-top: 78px; }
  .topbar.demo-admin-mode {
    height: 78px;
    min-height: 78px;
    grid-template-areas:
      "brand theme"
      "nav nav";
  }
}

@media (max-width: 390px) {
  .demo-change-user { max-width: 116px; }
}

.hero-main,
.activity-card,
.panel,
.topic-card,
.question-card,
.summary-card,
.login-card,
.modal {
  border: 0 !important;
}

/* Bordes visualmente redundantes: ya existe separación por fondo, sombra,
   estado o espaciado. Se mantienen inputs, tablas y zonas de arrastre. */
.topbar,
.demo-login-topbar,
.demo-role-button,
.demo-change-user,
.question-switch,
.theme-toggle,
.modal-close,
.modal-close-danger,
.btn-secondary,
.answer,
.feedback.success,
.feedback.error,
.review-option,
.exam-count-presets button,
.exam-topic-option,
.exam-summary-strip,
.stats-scope-tabs,
.stats-user-result,
.topic-attachments,
.admin-attachment-list,
.admin-option-role,
.admin-options-block {
  border: 0 !important;
}
.heat-day:not(.future) { border: 0 !important; }
.demo-change-user {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  transition: color .16s ease, background-color .16s ease, transform .16s ease;
}
.demo-change-user-icon { width: 14px; height: 14px; flex: 0 0 14px; }
.demo-change-user:hover { border: 0 !important; transform: translateX(-1px); }
.demo-role-button:hover:not(:disabled) { border: 0 !important; }
.btn-secondary { background: var(--surface-strong); }
.btn-secondary:hover { border: 0 !important; background: var(--brand-soft); }
.answer:hover:not(:disabled) { border: 0 !important; }
.stats-scope-tabs { background: var(--surface-strong); }
.stats-user-result { background: var(--surface-soft); box-shadow: none; }
.stats-user-result:hover { border: 0 !important; background: var(--surface-strong); }
.stats-user-result.selected { border: 0 !important; background: var(--brand-soft); box-shadow: none; }
.review-explanation { border-left: 0 !important; border-radius: 10px; }
.admin-tools { border-bottom: 0 !important; }
'''
    if "OpoTest public demo: role chooser" in text:
        raise RuntimeError("frontend styles: el parche de demo ya parece aplicado.")
    path.write_text(text.rstrip() + styles + "\n", encoding="utf-8")


def copy_runtime(repo: Path, runtime_source: Path) -> None:
    app_root = repo / "src" if (repo / "src" / "backend").is_dir() else repo
    destination = app_root / "backend" / "demo_runtime.py"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(runtime_source, destination)


def main() -> None:
    parser = argparse.ArgumentParser(description="Aplica la capa OpoTest Demo sin tocar su DB base.")
    parser.add_argument("repo", type=Path)
    parser.add_argument("runtime", type=Path)
    parser.add_argument("--base-path", default=DEFAULT_BASE_PATH)
    args = parser.parse_args()

    repo = args.repo.resolve()
    base_path = "/" + args.base_path.strip("/") if args.base_path.strip("/") else ""
    app_root = repo / "src" if (repo / "src" / "backend").is_dir() else repo
    required = [
        app_root / "backend" / "auth.py",
        app_root / "backend" / "admin.py",
        app_root / "frontend" / "script.js",
        app_root / "frontend" / "index.html",
        app_root / "frontend" / "styles.css",
    ]
    missing = [str(item) for item in required if not item.is_file()]
    if missing:
        raise SystemExit("Faltan archivos esperados de la aplicación base:\n- " + "\n- ".join(missing))

    sanitize_legacy_references(repo)
    copy_runtime(repo, args.runtime.resolve())
    patch_auth(app_root / "backend" / "auth.py")
    patch_admin(app_root / "backend" / "admin.py")
    patch_frontend_script(app_root / "frontend" / "script.js", base_path)
    patch_frontend_html(app_root / "frontend" / "index.html", base_path)
    patch_frontend_styles(app_root / "frontend" / "styles.css", base_path)
    assert_no_legacy_references(repo)
    print(f"OpoTest Demo aplicado correctamente sobre {repo} con base path {base_path or '/'}")


if __name__ == "__main__":
    main()
