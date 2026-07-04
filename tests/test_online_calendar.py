import unittest
from datetime import datetime
from unittest.mock import patch

from ai.online_calendar import get_online_calendar_answer


class TestOnlineCalendarRegression(unittest.TestCase):
    @patch("ai.online_calendar.fetch_online_datetime")
    def test_current_year_uses_runtime_year(self, mock_fetch_online_datetime):
        mock_fetch_online_datetime.return_value = datetime(2026, 2, 20, 9, 0, 0)

        answer = get_online_calendar_answer("which is the current year?")

        self.assertEqual(answer, "The current year is 2026.")

    @patch("ai.online_calendar._find_eid_al_fitr_gregorian")
    @patch("ai.online_calendar.fetch_online_datetime")
    def test_eid_query_returns_upcoming_eid(self, mock_fetch_online_datetime, mock_find_eid):
        mock_fetch_online_datetime.return_value = datetime(2026, 2, 20, 9, 0, 0)

        def _eid_for_year(year, timeout_seconds=10):
            if year == 2026:
                return datetime(2026, 3, 20)
            if year == 2027:
                return datetime(2027, 3, 10)
            return None

        mock_find_eid.side_effect = _eid_for_year

        answer = get_online_calendar_answer("when is eid ul fitr coming?")

        self.assertIn("Eid al-Fitr is expected to begin on", answer)
        self.assertIn("Friday, March 20, 2026", answer)

    @patch("ai.online_calendar._find_eid_al_fitr_gregorian")
    @patch("ai.online_calendar.fetch_online_datetime")
    def test_eid_query_next_year_returns_next_year_date(
        self, mock_fetch_online_datetime, mock_find_eid
    ):
        mock_fetch_online_datetime.return_value = datetime(2026, 2, 20, 9, 0, 0)

        def _eid_for_year(year, timeout_seconds=10):
            if year == 2027:
                return datetime(2027, 3, 10)
            return None

        mock_find_eid.side_effect = _eid_for_year

        answer = get_online_calendar_answer("when is eid ul fitr coming on next year?")

        self.assertIn("Eid al-Fitr is expected to begin on", answer)
        self.assertIn("Wednesday, March 10, 2027", answer)

    @patch("ai.online_calendar._find_eid_al_fitr_gregorian")
    @patch("ai.online_calendar.fetch_online_datetime")
    def test_eid_query_two_years_from_now_returns_target_year(
        self, mock_fetch_online_datetime, mock_find_eid
    ):
        mock_fetch_online_datetime.return_value = datetime(2026, 2, 20, 9, 0, 0)

        def _eid_for_year(year, timeout_seconds=10):
            if year == 2028:
                return datetime(2028, 2, 25)
            return None

        mock_find_eid.side_effect = _eid_for_year

        answer = get_online_calendar_answer("when is eid ul fitr in 2 years from now?")

        self.assertIn("Eid al-Fitr is expected to begin on", answer)
        self.assertIn("Friday, February 25, 2028", answer)

    @patch("ai.online_calendar.fetch_online_datetime")
    def test_new_year_query_points_to_next_new_year(self, mock_fetch_online_datetime):
        mock_fetch_online_datetime.return_value = datetime(2026, 2, 20, 9, 0, 0)

        answer = get_online_calendar_answer("when is new year?")

        self.assertIn("New Year's Day is on", answer)
        self.assertIn("January 01, 2027", answer)

    @patch("ai.online_calendar.fetch_online_datetime")
    def test_new_year_query_two_years_from_now_returns_target_year(
        self, mock_fetch_online_datetime
    ):
        mock_fetch_online_datetime.return_value = datetime(2026, 2, 20, 9, 0, 0)

        answer = get_online_calendar_answer("when is new year after 2 years?")

        self.assertIn("New Year's Day is on", answer)
        self.assertIn("January 01, 2028", answer)

    @patch("ai.online_calendar.fetch_online_datetime")
    def test_day_query_two_years_ago_uses_reference_year(self, mock_fetch_online_datetime):
        mock_fetch_online_datetime.return_value = datetime(2026, 2, 20, 9, 0, 0)

        answer = get_online_calendar_answer("what day was today 2 years ago?")

        self.assertEqual(answer, "On this day in 2024, it was Tuesday.")

    @patch("ai.online_calendar.fetch_online_datetime")
    def test_date_query_after_two_years_uses_reference_year(self, mock_fetch_online_datetime):
        mock_fetch_online_datetime.return_value = datetime(2026, 2, 20, 9, 0, 0)

        answer = get_online_calendar_answer("what is the date after 2 years?")

        self.assertEqual(answer, "On this date in 2028, it was 2028-02-20.")

    @patch("ai.online_calendar._find_eid_al_adha_gregorian")
    @patch("ai.online_calendar.fetch_online_datetime")
    def test_bakra_eid_query_returns_eid_al_adha(self, mock_fetch_online_datetime, mock_find_adha):
        mock_fetch_online_datetime.return_value = datetime(2026, 2, 20, 9, 0, 0)

        def _adha_for_year(year, timeout_seconds=10):
            if year == 2026:
                return datetime(2026, 5, 27)
            if year == 2027:
                return datetime(2027, 5, 17)
            return None

        mock_find_adha.side_effect = _adha_for_year

        answer = get_online_calendar_answer("when is bakra eid coming?")

        self.assertIn("Eid al-Adha is expected to begin on", answer)
        self.assertIn("Wednesday, May 27, 2026", answer)

    @patch("ai.online_calendar._find_eid_al_adha_gregorian")
    @patch("ai.online_calendar.fetch_online_datetime")
    def test_eid_ul_adha_query_returns_eid_al_adha(
        self, mock_fetch_online_datetime, mock_find_adha
    ):
        mock_fetch_online_datetime.return_value = datetime(2026, 2, 20, 9, 0, 0)

        def _adha_for_year(year, timeout_seconds=10):
            if year == 2026:
                return datetime(2026, 5, 27)
            if year == 2027:
                return datetime(2027, 5, 17)
            return None

        mock_find_adha.side_effect = _adha_for_year

        answer = get_online_calendar_answer("and when is eid ul adha coming?")

        self.assertIn("Eid al-Adha is expected to begin on", answer)
        self.assertIn("Wednesday, May 27, 2026", answer)

    @patch("ai.online_calendar._find_hijri_for_gregorian_date")
    @patch("ai.online_calendar.fetch_online_datetime")
    def test_ramadan_day_query_returns_day_number_when_in_ramadan(
        self, mock_fetch_online_datetime, mock_find_hijri_for_date
    ):
        mock_fetch_online_datetime.return_value = datetime(2026, 2, 20, 9, 0, 0)
        mock_find_hijri_for_date.return_value = (9, 10)

        answer = get_online_calendar_answer("what day of ramadan is today?")

        self.assertIn("Today is Ramadan day 10", answer)

    @patch("ai.online_calendar._find_ramadan_start_gregorian")
    @patch("ai.online_calendar._find_hijri_for_gregorian_date")
    @patch("ai.online_calendar.fetch_online_datetime")
    def test_ramadan_day_query_outside_ramadan_reports_upcoming_start(
        self,
        mock_fetch_online_datetime,
        mock_find_hijri_for_date,
        mock_find_ramadan_start,
    ):
        mock_fetch_online_datetime.return_value = datetime(2026, 2, 20, 9, 0, 0)
        mock_find_hijri_for_date.return_value = (8, 21)

        def _ramadan_start_for_year(year, timeout_seconds=10):
            if year == 2026:
                return datetime(2026, 2, 28)
            if year == 2027:
                return datetime(2027, 2, 17)
            return None

        mock_find_ramadan_start.side_effect = _ramadan_start_for_year

        answer = get_online_calendar_answer("what day of ramadan is today?")

        self.assertIn("Today is not within Ramadan", answer)
        self.assertIn("Saturday, February 28, 2026", answer)


if __name__ == "__main__":
    unittest.main()
