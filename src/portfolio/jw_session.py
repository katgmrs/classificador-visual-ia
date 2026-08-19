from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass


class JWSessionError(RuntimeError):
    pass


@dataclass
class SessionStatus:
    state: str = "disconnected"
    message: str = "Não conectado"
    current_url: str = ""


class JWBrowserSession:
    """Mantém uma sessão Playwright em uma única thread.

    A senha existe apenas durante ``login``. O contexto autenticado permanece em
    memória e é encerrado junto com a aplicação.
    """

    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="jw-browser")
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._property_id = ""
        self._status = SessionStatus()
        self._lock = threading.Lock()

    def _set_status(self, state: str, message: str, current_url: str = "") -> None:
        with self._lock:
            self._status = SessionStatus(state, message, current_url)

    def status(self) -> dict:
        with self._lock:
            return self._status.__dict__.copy()

    def login(self, email: str, password: str, property_id: str) -> dict:
        if not email.strip() or not password:
            raise JWSessionError("Informe e-mail e senha do JW Player.")
        if len(property_id.strip()) != 8:
            raise JWSessionError("O Property ID deve ter oito caracteres.")
        future = self._executor.submit(self._login, email.strip(), password, property_id.strip())
        return future.result(timeout=120)

    def _ensure_browser(self) -> None:
        if self._page and not self._page.is_closed():
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise JWSessionError("Playwright não está instalado.") from exc
        try:
            self._playwright = sync_playwright().start()
            # A automação permanece em segundo plano; nenhuma janela ou guia é
            # aberta para o usuário durante login, captura ou reprodução.
            self._browser = self._playwright.chromium.launch(
                headless=True,
                args=["--autoplay-policy=no-user-gesture-required"],
            )
        except Exception as exc:
            if self._playwright:
                try:
                    self._playwright.stop()
                except Exception:
                    pass
                self._playwright = None
            raise JWSessionError(
                "Não foi possível abrir o navegador automatizado. Reinicie a aplicação pelo arquivo "
                "iniciar_aplicacao.bat. Se o problema continuar, execute: python -m playwright install chromium"
            ) from exc
        self._context = self._browser.new_context(viewport={"width": 1440, "height": 900})
        self._page = self._context.new_page()

    def _login(self, email: str, password: str, property_id: str) -> dict:
        self._set_status("connecting", "Abrindo o JW Player")
        self._ensure_browser()
        self._property_id = property_id
        target = f"https://dashboard.jwplayer.com/p/{property_id}/media"
        try:
            self._page.goto(target, wait_until="domcontentloaded", timeout=60000)
            self._page.wait_for_timeout(1500)
            if "/login" in self._page.url.lower():
                username = self._page.locator('input[name="username"]')
                username.wait_for(state="visible", timeout=30000)
                username.fill(email)
                self._page.locator('button[type="submit"]:has-text("Continue")').click()
                password_field = self._page.locator('input[name="password"]')
                password_field.wait_for(state="visible", timeout=30000)
                password_field.fill(password)
                self._page.locator('button[type="submit"]:has-text("Login")').click()
                self._page.wait_for_timeout(5000)
            current = self._page.url
            if "/login" in current.lower() or "challenge" in current.lower():
                self._set_status(
                    "attention",
                    "O JW Player solicitou MFA ou CAPTCHA. A autenticação invisível não pode concluir essa verificação.",
                    current,
                )
            else:
                self._set_status("connected", "Sessão JW Player conectada", current)
            return self.status()
        except Exception as exc:
            self._set_status("error", str(exc), self._page.url if self._page else "")
            raise JWSessionError(str(exc)) from exc
        finally:
            password = None

    def verify(self) -> dict:
        return self._executor.submit(self._verify).result(timeout=30)

    def _verify(self) -> dict:
        if not self._page or self._page.is_closed():
            self._set_status("disconnected", "Navegador JW Player fechado")
            return self.status()
        current = self._page.url
        if "/login" in current.lower() or "challenge" in current.lower():
            self._set_status("attention", "O JW Player solicitou MFA ou CAPTCHA durante a autenticação invisível.", current)
        else:
            self._set_status("connected", "Sessão JW Player conectada", current)
        return self.status()

    def capture_media(self, media_id: str) -> dict:
        if self.status()["state"] != "connected":
            raise JWSessionError("Conecte uma sessão JW Player antes de acessar a mídia.")
        return self._executor.submit(self._capture_media, media_id).result(timeout=120)

    def _capture_media(self, media_id: str) -> dict:
        if not self._page or self._page.is_closed():
            self._set_status("attention", "O navegador JW Player foi fechado. Conecte novamente para continuar.")
            raise JWSessionError("O navegador JW Player foi fechado. Conecte novamente para continuar.")
        manifests: list[str] = []
        media_files: list[str] = []

        def capture(request):
            url = request.url
            if ".m3u8" in url.lower() and url not in manifests:
                manifests.append(url)
            if ".mp4" in url.lower() and url not in media_files:
                media_files.append(url)

        self._page.on("request", capture)
        target = f"https://dashboard.jwplayer.com/p/{self._property_id}/media/{media_id}"
        try:
            self._page.goto(target, wait_until="domcontentloaded", timeout=60000)
            self._page.wait_for_timeout(4000)
            if "/login" in self._page.url.lower():
                self._set_status("attention", "A sessão expirou. Faça login novamente.", self._page.url)
                raise JWSessionError("A sessão JW Player expirou.")
            # O dashboard nem sempre inicia o preview automaticamente.
            for selector in (
                'button[aria-label*="Play" i]',
                'button[title*="Play" i]',
                'button:has-text("Play")',
                'button:has-text("Reproduzir")',
                '[data-testid*="play" i]',
            ):
                try:
                    button = self._page.locator(selector).first
                    if button.is_visible(timeout=800):
                        button.click(timeout=3000)
                        break
                except Exception:
                    continue
            try:
                self._page.locator("video").first.evaluate("video => video.play().catch(() => {})", timeout=2000)
            except Exception:
                pass
            self._page.wait_for_timeout(10000)
            try:
                resources = self._page.evaluate(
                    "performance.getEntriesByType('resource').map(item => item.name)"
                )
                for url in resources:
                    lower = url.lower()
                    if ".m3u8" in lower and url not in manifests:
                        manifests.append(url)
                    elif ".mp4" in lower and url not in media_files:
                        media_files.append(url)
            except Exception:
                pass

            playable = []
            for url in manifests:
                try:
                    response = self._page.request.get(url, timeout=30000)
                    if response.status == 200 and (
                        "#EXT-X-STREAM-INF" in response.text()
                        or "#EXTINF" in response.text()
                        or "#EXTM3U" in response.text()
                    ):
                        playable.append(url)
                except Exception:
                    continue
            source_url = playable[0] if playable else (media_files[0] if media_files else None)
            if not source_url:
                raise JWSessionError(
                    "Nenhuma fonte HLS ou MP4 foi capturada. Abra o preview da mídia no navegador JW Player e tente novamente."
                )
            return {
                "media_id": media_id, "dashboard_url": target,
                "master_url": source_url, "captured": len(manifests) + len(media_files),
            }
        except Exception as exc:
            message = str(exc)
            if "Target page" in message or "browser has been closed" in message:
                self._set_status("attention", "O navegador JW Player foi fechado. Conecte novamente para continuar.")
                raise JWSessionError("O navegador JW Player foi fechado. Conecte novamente para continuar.") from exc
            raise
        finally:
            if self._page and not self._page.is_closed():
                self._page.remove_listener("request", capture)

    def close(self) -> None:
        try:
            self._executor.submit(self._close).result(timeout=15)
        finally:
            self._executor.shutdown(wait=False, cancel_futures=True)

    def _close(self) -> None:
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        self._page = self._context = self._browser = self._playwright = None
        self._set_status("disconnected", "Sessão encerrada")
