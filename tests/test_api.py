import unittest

from fastapi.testclient import TestClient

from app import ANALYSIS_LOCK, PROCESSOR, app, is_session_interruption
from src.portfolio.ai import AIError
from src.portfolio.jw_session import JWSessionError


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_home_and_portfolio_endpoints(self):
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertIn("Portfólio de vídeos Cetrus", home.text)
        stats = self.client.get("/api/stats")
        self.assertEqual(stats.status_code, 200)
        self.assertIn("records", stats.json())
        self.assertEqual(
            stats.json()["jw_library_url"],
            "https://dashboard.jwplayer.com/p/XdfUPSCL/media",
        )
        videos = self.client.get("/api/videos", params={"search": "y6zIncnf"})
        self.assertEqual(videos.status_code, 200)
        self.assertIn("items", videos.json())

    def test_video_processor_is_strictly_sequential(self):
        self.assertEqual(PROCESSOR._max_workers, 1)
        self.assertFalse(ANALYSIS_LOCK.locked())

    def test_processing_requires_authenticated_jw_session(self):
        response = self.client.post(
            "/api/process",
            json={"media_ids": ["y6zIncnf"], "provider": "Claude", "api_key": ""},
        )
        self.assertEqual(response.status_code, 409)

    def test_processing_rejects_removed_ai_providers(self):
        response = self.client.post(
            "/api/process",
            json={"media_ids": ["y6zIncnf"], "provider": "OpenAI", "api_key": "key"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "Selecione Claude ou Ollama.")

    def test_session_interruption_is_not_a_media_error(self):
        self.assertTrue(is_session_interruption(JWSessionError("Conecte uma sessão JW Player antes de acessar a mídia.")))
        self.assertTrue(is_session_interruption(JWSessionError("O navegador JW Player foi fechado.")))
        self.assertFalse(is_session_interruption(JWSessionError("Nenhuma fonte HLS ou MP4 foi capturada.")))
        self.assertFalse(is_session_interruption(AIError("Ollama: modelo não encontrado")))


if __name__ == "__main__":
    unittest.main()
