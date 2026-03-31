"""Tests for profile manager."""

import pytest
from unittest.mock import patch, MagicMock


class TestProfileManager:
    """Test ProfileManager loading and methods."""

    def _make_profile_manager(self, profile_data):
        """Helper to create a ProfileManager with mocked config."""
        with patch("src.core.profile.config") as mock_cfg:
            mock_cfg.profile = profile_data
            from src.core.profile import ProfileManager
            return ProfileManager()

    def test_loads_personal_info(self):
        """Should parse personal info from profile config."""
        pm = self._make_profile_manager({
            "personal": {"first_name": "John", "last_name": "Doe", "email": "john@example.com"},
        })
        assert pm.personal.first_name == "John"
        assert pm.personal.email == "john@example.com"

    def test_loads_skills(self):
        """Should parse skills with all categories."""
        pm = self._make_profile_manager({
            "skills": {
                "primary": ["Python", "Java"],
                "secondary": ["Docker"],
                "frameworks": ["pytest"],
                "tools": ["JIRA"],
            },
        })
        assert "Python" in pm.skills.primary
        assert "Python" in pm.skills.all_skills
        assert len(pm.skills.top_skills) <= 5

    def test_loads_education(self):
        """Should parse education list correctly."""
        pm = self._make_profile_manager({
            "education": [
                {"degree": "B.E.", "field": "CS", "university": "MIT", "graduation_year": 2020}
            ],
        })
        assert len(pm.education) == 1
        assert pm.education[0].degree == "B.E."
        assert pm.education[0].field_of_study == "CS"

    def test_loads_experience(self):
        """Should parse experience list."""
        pm = self._make_profile_manager({
            "experience": [
                {"company": "Corp", "title": "SDET", "start_date": "2022", "highlights": ["Built framework"]},
            ],
        })
        assert len(pm.experience) == 1
        assert pm.experience[0].company == "Corp"
        assert pm.experience[0].highlights[0] == "Built framework"

    def test_to_flat_dict(self):
        """Should flatten profile into a key-value dict."""
        pm = self._make_profile_manager({
            "personal": {"first_name": "John", "email": "j@e.com"},
            "skills": {"primary": ["Python"], "secondary": [], "frameworks": [], "tools": []},
            "common_answers": {"why_interested": "Great company"},
        })
        flat = pm.to_flat_dict()
        assert flat["first_name"] == "John"
        assert flat["email"] == "j@e.com"
        assert "Python" in flat["skills"]
        assert flat["why_interested"] == "Great company"

    def test_get_search_keywords(self):
        """Should return search keywords from job_search config."""
        pm = self._make_profile_manager({
            "job_search": {"keywords": ["SDET", "QA"]},
        })
        assert pm.get_search_keywords() == ["SDET", "QA"]

    def test_get_exclude_keywords(self):
        """Should return exclude keywords."""
        pm = self._make_profile_manager({
            "job_search": {"exclude_keywords": ["Intern", "Fresher"]},
        })
        assert "Intern" in pm.get_exclude_keywords()

    def test_generate_cover_letter(self):
        """Should generate cover letter from template."""
        pm = self._make_profile_manager({
            "personal": {"full_name": "John Doe"},
            "professional": {"years_of_experience": 5},
            "skills": {"primary": ["Python", "Selenium"], "secondary": [], "frameworks": [], "tools": []},
            "experience": [{"highlights": ["Built a framework"]}],
            "cover_letter_template": "Dear {company}, applying for {role}. {full_name}",
        })
        result = pm.generate_cover_letter("Google", "SDET")
        assert "Google" in result
        assert "SDET" in result
        assert "John Doe" in result

    def test_cover_letter_empty_experience_has_default(self):
        """Cover letter should have a default key_achievement when no experience."""
        pm = self._make_profile_manager({
            "personal": {"full_name": "Jane"},
            "professional": {"years_of_experience": 0},
            "skills": {"primary": [], "secondary": [], "frameworks": [], "tools": []},
            "cover_letter_template": "Achievement: {key_achievement}",
        })
        result = pm.generate_cover_letter("Co", "Role")
        assert "delivering high-quality" in result

    def test_cover_letter_bad_template_no_crash(self):
        """Cover letter with unknown placeholders should not crash."""
        pm = self._make_profile_manager({
            "personal": {"full_name": "Jane"},
            "professional": {"years_of_experience": 0},
            "skills": {"primary": [], "secondary": [], "frameworks": [], "tools": []},
            "cover_letter_template": "Hi {company}, {unknown_field}!",
        })
        # Should not raise - falls back to safe_substitute
        result = pm.generate_cover_letter("Co", "Role")
        assert "Co" in result

    def test_empty_profile_no_crash(self):
        """Empty profile data should not crash."""
        pm = self._make_profile_manager({})
        assert pm.personal.first_name == ""
        assert pm.get_search_keywords() == []
        flat = pm.to_flat_dict()
        assert isinstance(flat, dict)
