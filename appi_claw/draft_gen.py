"""Application draft generator using Gemini API."""

from google import genai
from appi_claw.platforms.base import Listing

SYSTEM_PROMPT = """\
You are an expert career coach writing job/internship applications for an Indian student.
Your goal: write a concise, compelling application message that gets the candidate noticed.

Rules:
- Keep it under 200 words unless the platform requires more
- Be genuine, not generic — reference specific details from the listing
- Highlight relevant skills/projects from the candidate's profile
- Match the tone to the platform (formal for email, conversational for DMs, professional for portals)
- Never lie or fabricate experience
- End with a clear call-to-action or expression of interest
- Do NOT include subject lines unless the platform is "cold_email"
"""

PLATFORM_HINTS = {
    "internshala": "This is for an Internshala application form. Write a cover letter / 'Why should you be hired' answer. Keep it focused and professional.",
    "linkedin": "This is for a LinkedIn Easy Apply. Write a short, punchy note that fits in the additional info / cover note field.",
    "wellfound": "This is for Wellfound (AngelList). Write a startup-friendly cover note — show hustle and builder mentality.",
    "cold_email": "This is a cold email to a hiring manager or founder. Include a subject line on the first line, then the body. Be respectful of their time.",
    "dm": "This is a Twitter or LinkedIn DM to a founder. Keep it very short (3-4 sentences max), casual but professional.",
}


def _build_prompt(listing: Listing, user_profile: dict, platform: str) -> str:
    """Build the user prompt for draft generation."""
    platform_hint = PLATFORM_HINTS.get(platform, PLATFORM_HINTS["internshala"])

    profile_text = f"""
Candidate Profile:
- Name: {user_profile.get('name', 'N/A')}
- Degree: {user_profile.get('degree', 'N/A')}
- Skills: {', '.join(user_profile.get('skills', []))}
- Projects: {', '.join(user_profile.get('projects', []))}
- Experience: {user_profile.get('experience', 'N/A')}
- Location: {user_profile.get('location', 'N/A')}
- GitHub: {user_profile.get('github', 'N/A')}
""".strip()

    listing_text = f"""
Listing Details:
- Company: {listing.company or 'Unknown'}
- Role: {listing.role or 'Unknown'}
- Platform: {listing.platform or platform}
- Description: {listing.description or 'Not provided'}
- URL: {listing.url}
""".strip()

    return f"""{platform_hint}

{profile_text}

{listing_text}

Write the application message now."""


def generate_draft(listing: Listing, config: dict, platform: str | None = None) -> str:
    """Generate a platform-appropriate application draft.

    Args:
        listing: The job/internship listing.
        config: Full app config (needs gemini and user_profile sections).
        platform: Override platform detection. Defaults to listing.platform.

    Returns:
        The generated draft text.
    """
    gemini_config = config["gemini"]
    user_profile = config["user_profile"]
    platform = platform or listing.platform or "internshala"

    client = genai.Client(api_key=gemini_config["api_key"])
    prompt = _build_prompt(listing, user_profile, platform)

    response = client.models.generate_content(
        model=gemini_config.get("model", "gemini-2.5-flash"),
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.7,
            max_output_tokens=1024,
        ),
    )

    return response.text.strip()


def revise_draft(current_draft: str, feedback: str, listing: Listing, config: dict, platform: str | None = None) -> str:
    """Revise an existing draft based on user feedback.

    Args:
        current_draft: The draft to revise.
        feedback: User's feedback (e.g. "make it more fintech-specific").
        listing: The job/internship listing.
        config: Full app config.
        platform: Platform name.

    Returns:
        The revised draft text.
    """
    gemini_config = config["gemini"]
    user_profile = config["user_profile"]
    platform = platform or listing.platform or "internshala"

    client = genai.Client(api_key=gemini_config["api_key"])

    revision_prompt = f"""You previously wrote this application draft:

--- DRAFT ---
{current_draft}
--- END DRAFT ---

The user wants you to revise it with this feedback:
"{feedback}"

Candidate profile:
- Name: {user_profile.get('name', 'N/A')}
- Degree: {user_profile.get('degree', 'N/A')}
- Skills: {', '.join(user_profile.get('skills', []))}
- Projects: {', '.join(user_profile.get('projects', []))}
- Experience: {user_profile.get('experience', 'N/A')}

Listing: {listing.company or 'Unknown'} — {listing.role or 'Unknown'} ({platform})

Rewrite the draft incorporating the feedback. Keep the same length and platform style."""

    response = client.models.generate_content(
        model=gemini_config.get("model", "gemini-2.5-flash"),
        contents=revision_prompt,
        config=genai.types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.7,
            max_output_tokens=1024,
        ),
    )

    return response.text.strip()
