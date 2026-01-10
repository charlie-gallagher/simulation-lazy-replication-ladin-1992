import unittest
from timestamp import new_timestamp, MultiPartTimestamp


class TimestampTestCase(unittest.TestCase):
    def test_create_timestamp(self):
        n = 5
        x = new_timestamp(n)
        with self.subTest("length"):
            self.assertEqual(len(x), 5)
        with self.subTest("str"):
            self.assertEqual(str(x), "[0, 0, 0, 0, 0]")
        with self.subTest("init 0"):
            self.assertEqual(x.parts, [0, 0, 0, 0, 0])

    def test_incr(self):
        x = new_timestamp(5)
        x.incr(0)
        self.assertEqual(x.get(0), 1)

    def test_merge(self):
        cases = {
            "x_gt_y": (
                MultiPartTimestamp([1, 2, 3]),
                MultiPartTimestamp([1, 1, 1]),
                MultiPartTimestamp([1, 2, 3]),
            ),
            "y_gt_x": (
                MultiPartTimestamp([1, 1, 1]),
                MultiPartTimestamp([1, 2, 3]),
                MultiPartTimestamp([1, 2, 3]),
            ),
            "x_eq_y": (
                MultiPartTimestamp([1, 2, 3]),
                MultiPartTimestamp([1, 2, 3]),
                MultiPartTimestamp([1, 2, 3]),
            ),
        }
        for desc, parts in cases.items():
            with self.subTest(desc):
                x = parts[0]
                y = parts[1]
                want = parts[2]
                got = x.merge(y)
                self.assertEqual(want, got)

    def test_comparisons(self):
        cases = {
            "x_gt_y": (
                self.assertGreater,
                MultiPartTimestamp([1, 2, 3]),
                MultiPartTimestamp([1, 1, 1]),
            ),
            "x_lt_y": (
                self.assertLess,
                MultiPartTimestamp([1, 1, 3]),
                MultiPartTimestamp([1, 2, 3]),
            ),
            "x_eq_y": (
                self.assertEqual,
                MultiPartTimestamp([1, 1, 3]),
                MultiPartTimestamp([1, 1, 3]),
            ),
            "x_ne_y": (
                self.assertNotEqual,
                MultiPartTimestamp([0, 1, 5]),
                MultiPartTimestamp([1, 2, 3]),
            ),
        }
        for desc, parts in cases.items():
            with self.subTest(desc):
                compare = parts[0]
                x = parts[1]
                y = parts[2]
                compare(x, y)

    def test_copy(self):
        x = new_timestamp(5)
        y = x.copy()
        with self.subTest("class"):
            self.assertIsInstance(y, MultiPartTimestamp)
        self.assertIsNot(y, x)

    def test_compare(self):
        cases = {
            "x_gt_y": (MultiPartTimestamp([1, 2, 3]), MultiPartTimestamp([1, 1, 1]), 1),
            "x_lt_y": (
                MultiPartTimestamp([1, 1, 3]),
                MultiPartTimestamp([1, 2, 3]),
                -1,
            ),
            "x_concurrent_with_y": (
                MultiPartTimestamp([0, 1, 5]),
                MultiPartTimestamp([1, 2, 3]),
                None,
            ),
        }
        for desc, parts in cases.items():
            with self.subTest(desc):
                x = parts[0]
                y = parts[1]
                want = parts[2]
                got = x.compare(y)
                self.assertEqual(want, got)
