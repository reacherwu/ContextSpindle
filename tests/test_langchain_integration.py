import unittest
from continuum.integrations.langchain import ContinuumChatMessageHistory
from continuum.api import ContinuumConfig


class TestLangChainIntegration(unittest.TestCase):
    def test_chat_history_lifecycle(self):
        cfg = ContinuumConfig(embedding_dim=16, state_dim=16, hot_capacity=10, cold_capacity=20)
        history = ContinuumChatMessageHistory(config=cfg)

        history.add_user_message("Hello, my peanut allergy is severe.")
        history.add_ai_message("Understood, I will never suggest peanuts.")

        for i in range(15):
            history.add_user_message(f"Casual message #{i}")
            history.add_ai_message(f"Casual reply #{i}")

        self.assertEqual(len(history.messages), 32)
        self.assertLessEqual(history.engine.get_stats()["total_slots"], 30)

        matches = history.query_relevant_context("Can I eat peanut butter cookies?", top_k=3)
        self.assertIsInstance(matches, list)

        history.clear()
        self.assertEqual(len(history.messages), 0)
        self.assertEqual(history.engine.get_stats()["step_count"], 0)


if __name__ == "__main__":
    unittest.main()
