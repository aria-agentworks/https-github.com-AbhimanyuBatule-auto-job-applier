"""
Profile Manager - Provides structured access to user profile data.
The AI form filler uses this to answer any question on any application form.
"""

from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

from src.core.config import config


@dataclass
class PersonalInfo:
    first_name: str = ""
    last_name: str = ""
    full_name: str = ""
    email: str = ""
    phone: str = ""
    phone_country_code: str = ""
    date_of_birth: str = ""
    gender: str = ""
    nationality: str = ""
    current_city: str = ""
    current_state: str = ""
    current_country: str = ""
    zip_code: str = ""
    address: str = ""
    linkedin_url: str = ""
    github_url: str = ""
    portfolio_url: str = ""
    website_url: str = ""


@dataclass
class ProfessionalInfo:
    current_title: str = ""
    desired_titles: list[str] = field(default_factory=list)
    years_of_experience: int = 0
    current_company: str = ""
    current_salary: str = ""
    expected_salary: str = ""
    salary_currency: str = "INR"
    notice_period_days: int = 0
    willing_to_relocate: bool = True
    preferred_locations: list[str] = field(default_factory=list)
    work_authorization: dict = field(default_factory=dict)
    preferred_work_type: list[str] = field(default_factory=list)
    employment_type: list[str] = field(default_factory=list)


@dataclass
class Education:
    degree: str = ""
    field_of_study: str = ""
    university: str = ""
    graduation_year: int = 0
    gpa: str = ""


@dataclass
class Experience:
    company: str = ""
    title: str = ""
    start_date: str = ""
    end_date: str = ""
    location: str = ""
    description: str = ""
    highlights: list[str] = field(default_factory=list)


@dataclass
class Skills:
    primary: list[str] = field(default_factory=list)
    secondary: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)

    @property
    def all_skills(self) -> list[str]:
        return list(set(self.primary + self.secondary + self.frameworks + self.tools))

    @property
    def top_skills(self) -> list[str]:
        """Return top skills for short-form fields."""
        return self.primary[:5]


class ProfileManager:
    """
    Loads profile from config and provides structured access.
    Acts as the single source of truth for all profile data.
    """

    def __init__(self):
        self._profile = config.profile
        self.personal = self._load_personal()
        self.professional = self._load_professional()
        self.skills = self._load_skills()
        self.education = self._load_education()
        self.experience = self._load_experience()
        self.certifications = self._profile.get("certifications", [])
        self.common_answers = self._profile.get("common_answers", {})
        self.job_search = self._profile.get("job_search", {})
        self.cover_letter_template = self._profile.get("cover_letter_template", "")

    def _load_personal(self) -> PersonalInfo:
        data = self._profile.get("personal", {})
        return PersonalInfo(**{k: v for k, v in data.items() if k in PersonalInfo.__dataclass_fields__})

    def _load_professional(self) -> ProfessionalInfo:
        data = self._profile.get("professional", {})
        return ProfessionalInfo(**{k: v for k, v in data.items() if k in ProfessionalInfo.__dataclass_fields__})

    def _load_skills(self) -> Skills:
        data = self._profile.get("skills", {})
        return Skills(**{k: v for k, v in data.items() if k in Skills.__dataclass_fields__})

    def _load_education(self) -> list[Education]:
        data = self._profile.get("education", [])
        result = []
        for edu in data:
            mapped = {
                "degree": edu.get("degree", ""),
                "field_of_study": edu.get("field", ""),
                "university": edu.get("university", ""),
                "graduation_year": edu.get("graduation_year", 0),
                "gpa": edu.get("gpa", ""),
            }
            result.append(Education(**mapped))
        return result

    def _load_experience(self) -> list[Experience]:
        data = self._profile.get("experience", [])
        return [Experience(**{k: v for k, v in exp.items() if k in Experience.__dataclass_fields__}) for exp in data]

    def get_resume_path(self, format: str = "pdf") -> Optional[Path]:
        """Get path to resume file."""
        resume = self._profile.get("resume", {})
        path_str = resume.get(f"{format}_path", "")
        if path_str:
            from src.core.config import PROJECT_ROOT
            return PROJECT_ROOT / path_str
        return None

    def generate_cover_letter(self, company: str, role: str, skills: list[str] = None) -> str:
        """Generate a cover letter from template."""
        if not self.cover_letter_template:
            return ""
        relevant_skills = ", ".join(skills or self.skills.top_skills)
        key_achievement = "delivering high-quality automation solutions"
        if self.experience:
            highlights = self.experience[0].highlights
            if highlights:
                key_achievement = highlights[0]

        from string import Template
        # Use safe_substitute to avoid KeyError on unknown placeholders
        tmpl = Template(self.cover_letter_template.replace("{", "${").replace("}", "}"))
        try:
            return self.cover_letter_template.format(
                company=company,
                role=role,
                experience_years=self.professional.years_of_experience,
                relevant_skills=relevant_skills,
                key_achievement=key_achievement,
                full_name=self.personal.full_name,
                skills=relevant_skills,
            )
        except (KeyError, IndexError):
            # Fall back to safe substitution if template has unknown keys
            return tmpl.safe_substitute(
                company=company,
                role=role,
                experience_years=self.professional.years_of_experience,
                relevant_skills=relevant_skills,
                key_achievement=key_achievement,
                full_name=self.personal.full_name,
                skills=relevant_skills,
            )

    def to_flat_dict(self) -> dict:
        """
        Flatten the entire profile into a simple key-value dict.
        This is what the AI uses to match form fields to profile data.
        """
        flat = {}

        # Personal
        for field_name in PersonalInfo.__dataclass_fields__:
            flat[field_name] = getattr(self.personal, field_name, "")

        # Professional
        for field_name in ProfessionalInfo.__dataclass_fields__:
            val = getattr(self.professional, field_name, "")
            flat[field_name] = val

        # Skills
        flat["skills"] = ", ".join(self.skills.all_skills)
        flat["primary_skills"] = ", ".join(self.skills.primary)
        flat["top_skills"] = ", ".join(self.skills.top_skills)
        flat["frameworks"] = ", ".join(self.skills.frameworks)
        flat["tools"] = ", ".join(self.skills.tools)

        # Education
        if self.education:
            edu = self.education[0]
            flat["degree"] = edu.degree
            flat["field_of_study"] = edu.field_of_study
            flat["university"] = edu.university
            flat["graduation_year"] = str(edu.graduation_year)
            flat["gpa"] = edu.gpa

        # Experience summary
        if self.experience:
            exp = self.experience[0]
            flat["current_company_name"] = exp.company
            flat["current_job_title"] = exp.title
            flat["current_job_description"] = exp.description

        # Common answers
        flat.update(self.common_answers)

        return flat

    def get_search_keywords(self) -> list[str]:
        """Get job search keywords."""
        return self.job_search.get("keywords", [])

    def get_exclude_keywords(self) -> list[str]:
        """Get keywords to exclude from search."""
        return self.job_search.get("exclude_keywords", [])
