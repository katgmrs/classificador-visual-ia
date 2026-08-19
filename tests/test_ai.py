import unittest
from unittest.mock import Mock, patch

from src.portfolio.ai import AIError, analysis_prompt, analyze_frames, parse_result, validate_ollama_model


FRAME = {"timestamp": 12.5, "mime_type": "image/jpeg", "data": "YWJj"}
RESULT = '{"category":"Demonstrativo","summary":"Demonstra um procedimento.","confidence":0.9}'


class MultimodalProviderTests(unittest.TestCase):
    @patch("src.portfolio.ai.requests.get")
    def test_ollama_model_is_validated_before_processing(self, get):
        get.return_value = Mock(status_code=200, json=lambda: {"models": [{"name": "qwen:latest"}]})
        with self.assertRaisesRegex(AIError, "não está instalado"):
            validate_ollama_model("http://127.0.0.1:11434", "llava:7b")

    def test_prompt_contains_standardization_and_visual_decision_rules(self):
        prompt = analysis_prompt("Aula", frame_times=[10, 20])
        self.assertIn("1 a 3 frases", prompt)
        self.assertIn("principal conteúdo abordado", prompt)
        self.assertIn("não deduza características do áudio", prompt)
        self.assertIn("não classifique como demonstrativo apenas", prompt.casefold())

    def test_summary_is_limited_to_three_sentences(self):
        result = parse_result('{"category":"Teórica core","summary":"Um. Dois. Três. Quatro.","confidence":1}')
        self.assertEqual(result["summary"], "Um. Dois. Três.")

    def test_summary_is_not_cut_in_the_middle_by_character_limit(self):
        long_sentence = "A aula apresenta " + "detalhadamente o conteúdo médico " * 15 + "e conclui o conceito"
        result = parse_result(
            '{"category":"Teórica core","summary":' + repr(long_sentence).replace("'", '"') + ',"confidence":1}'
        )
        self.assertGreater(len(result["summary"]), 320)
        self.assertTrue(result["summary"].endswith("conceito."))

    @patch("src.portfolio.ai.requests.post")
    def test_openai_uses_responses_image_input(self, post):
        post.return_value = Mock(status_code=200, json=lambda: {"output_text": RESULT})
        result = analyze_frames("OpenAI", "key", "gpt-test", "Aula", [FRAME])
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["input"][0]["content"][1]["type"], "input_image")
        self.assertEqual(result["category"], "Demonstrativo")

    @patch("src.portfolio.ai.requests.post")
    def test_gemini_uses_inline_image(self, post):
        post.return_value = Mock(status_code=200, json=lambda: {
            "candidates": [{"content": {"parts": [{"text": RESULT}]}}]
        })
        analyze_frames("Gemini", "key", "gemini-test", "Aula", [FRAME])
        parts = post.call_args.kwargs["json"]["contents"][0]["parts"]
        self.assertIn("inline_data", parts[1])

    @patch("src.portfolio.ai.requests.post")
    def test_claude_uses_base64_image(self, post):
        post.return_value = Mock(status_code=200, json=lambda: {
            "content": [{"type": "text", "text": RESULT}]
        })
        analyze_frames("Claude", "key", "claude-test", "Aula", [FRAME])
        image = post.call_args.kwargs["json"]["messages"][0]["content"][1]
        self.assertEqual(image["source"]["type"], "base64")

    @patch("src.portfolio.ai.requests.post")
    def test_ollama_limits_visual_input_and_reduces_on_context_error(self, post):
        limited = Mock(status_code=400, text="request exceeds the available context size")
        success = Mock(status_code=200, text="", json=lambda: {"message": {"content": RESULT}})
        post.side_effect = [limited, success]
        frames = [{**FRAME, "timestamp": index} for index in range(8)]
        result = analyze_frames("Ollama", "", "llava:7b", "Aula", frames)
        first_payload = post.call_args_list[0].kwargs["json"]
        retry_payload = post.call_args_list[1].kwargs["json"]
        self.assertEqual(first_payload["options"]["num_ctx"], 8192)
        self.assertEqual(len(first_payload["messages"][0]["images"]), 4)
        self.assertEqual(len(retry_payload["messages"][0]["images"]), 2)
        self.assertEqual(result["category"], "Demonstrativo")


if __name__ == "__main__":
    unittest.main()
