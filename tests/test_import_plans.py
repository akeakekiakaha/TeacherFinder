import unittest
from datetime import date

from scripts.import_plans import current_week_start, merge_week_changes, parse_change_line, parse_changes


class ParseChangeLineTests(unittest.TestCase):
    def test_replacement_retains_group_and_new_lesson_details(self):
        changes = parse_change_line(
            "2026-11-17",
            "4B",
            "Lekcja 4, 5 grupa 1 – zastępstwo tworzenie p. Ferdyn s. 6A",
        )

        self.assertEqual([4, 5], [change["lesson_number"] for change in changes])
        self.assertTrue(all(change["action"] == "replace" for change in changes))
        self.assertTrue(all(change["group"] == "1" for change in changes))
        self.assertTrue(all(change["new_subject"] == "tworzenie" for change in changes))
        self.assertTrue(all(change["new_teacher"] == "Ferdyn" for change in changes))
        self.assertTrue(all(change["new_room"] == "6A" for change in changes))
        self.assertTrue(all(change["original_text"].startswith("Lekcja 4, 5") for change in changes))

    def test_start_time_and_dismissal_generate_group_scoped_cancellations(self):
        starts_late = parse_change_line(
            "2026-11-17", "4E", "Grupa 1 rozpoczyna zajęcia od lekcji 5"
        )
        leaves_early = parse_change_line(
            "2026-11-17", "5D", "Grupa 2 zwolniona do domu po lekcji 7"
        )

        self.assertEqual([1, 2, 3, 4], [change["lesson_number"] for change in starts_late])
        self.assertEqual([8, 9, 10, 11, 12], [change["lesson_number"] for change in leaves_early])
        self.assertTrue(all(change["action"] == "cancel" for change in starts_late + leaves_early))
        self.assertTrue(all(change["group"] == "1" for change in starts_late))
        self.assertTrue(all(change["group"] == "2" for change in leaves_early))
        self.assertTrue(starts_late[0]["display_notice"])
        self.assertTrue(leaves_early[0]["display_notice"])
        self.assertTrue(all(not change["display_notice"] for change in leaves_early[1:]))

    def test_explicit_cancellation_targets_only_the_requested_group(self):
        changes = parse_change_line(
            "2026-11-17", "5D", "Lekcja 4 grupa 1 – odwołana"
        )

        self.assertEqual(1, len(changes))
        self.assertEqual(4, changes[0]["lesson_number"])
        self.assertEqual("1", changes[0]["group"])
        self.assertEqual("cancel", changes[0]["action"])

    def test_unrecognized_text_is_preserved_as_a_note(self):
        text = "Osoby nieuczęszczające na religię zwolnione do domu po lekcji 7"
        changes = parse_change_line("2026-11-17", "1B", text)

        self.assertEqual(1, len(changes))
        self.assertEqual("note", changes[0]["action"])
        self.assertEqual(text, changes[0]["original_text"])
        self.assertIsNone(changes[0]["lesson_number"])


class ParseChangesPageTests(unittest.TestCase):
    def test_reads_date_class_and_original_text_from_article(self):
        html = """
        <article id="article-20">
          <div property="text">
            <h3>2026-11-17</h3>
            <p>4B</p>
            <p>Lekcja 6 – doradztwo p. Wieczorek s. 23</p>
          </div>
        </article>
        """

        changes = parse_changes(html)

        self.assertEqual(1, len(changes))
        self.assertEqual("2026-11-17", changes[0]["date"])
        self.assertEqual("4B", changes[0]["class_name"])
        self.assertEqual(6, changes[0]["lesson_number"])
        self.assertEqual("doradztwo", changes[0]["new_subject"])
        self.assertEqual("Lekcja 6 – doradztwo p. Wieczorek s. 23", changes[0]["original_text"])

    def test_rejects_unrecognized_date_structure(self):
        with self.assertRaises(RuntimeError):
            parse_changes(
                '<article id="article-20"><div property="text"><p>2026-11-17</p></div></article>'
            )

    def test_empty_article_has_no_changes(self):
        self.assertEqual([], parse_changes('<article id="article-20"><h1>Zmiany do planu</h1></article>'))


class WeeklySnapshotTests(unittest.TestCase):
    def test_week_starts_on_current_monday_and_next_monday_on_sunday(self):
        self.assertEqual(date(2026, 11, 16), current_week_start(date(2026, 11, 19)))
        self.assertEqual(date(2026, 11, 23), current_week_start(date(2026, 11, 22)))

    def test_changes_merge_within_week_but_ignore_other_weeks(self):
        monday = {
            "date": "2026-11-16", "class_name": "4B", "lesson_number": 2,
            "group": "", "action": "replace", "original_text": "Poniedziałek"
        }
        tuesday = {
            "date": "2026-11-17", "class_name": "4B", "lesson_number": 3,
            "group": "", "action": "cancel", "original_text": "Wtorek"
        }
        old_week = {
            "date": "2026-11-13", "class_name": "4B", "lesson_number": 4,
            "group": "", "action": "cancel", "original_text": "Poprzedni tydzień"
        }
        updated_monday = {**monday, "original_text": "Zaktualizowany poniedziałek"}

        merged = merge_week_changes(
            [updated_monday, tuesday],
            [monday, old_week],
            date(2026, 11, 16),
        )

        self.assertEqual([updated_monday, tuesday], merged)


if __name__ == "__main__":
    unittest.main()
