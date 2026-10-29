import unittest
from optimization.optimizer import optimize_datasets


class OptimizerTests(unittest.TestCase):
    def test_budget_is_respected_and_value_maximised(self):
        result = optimize_datasets([
            {"dataset_id": "A", "licensing_cost": 4, "value_score": 5},
            {"dataset_id": "B", "licensing_cost": 3, "value_score": 4},
            {"dataset_id": "C", "licensing_cost": 6, "value_score": 8},
        ], 7)
        self.assertLessEqual(result["total_cost"], 7)
        self.assertEqual(set(result["selected_dataset_ids"]), {"A", "B"})
        self.assertEqual(result["total_value"], 9)

    def test_empty_candidates(self):
        result = optimize_datasets([], 100)
        self.assertEqual(result["selected_dataset_ids"], [])
        self.assertEqual(result["total_cost"], 0)


if __name__ == "__main__":
    unittest.main()
