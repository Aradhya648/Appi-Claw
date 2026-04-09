"""Application draft generator using Gemini API."""

from google import genai
from appi_claw.platforms.base import Listing

SYSTEM_PROMPT = """\
You are writing a job/internship application for Aradhya Mishra — a BBA Strategy & Business Analytics student at Christ University who is ALSO the Founder & CEO of Drufiy AI.

CRITICAL IDENTITY: Aradhya is NOT a typical student applicant. He has real traction — 50+ active users, 300+ waitlist, bootstrapped Rs 75K, Round 3 NSRCEL IIM Bangalore finalist, building a Jarvis-like AI agent system. He also built Markora (equity analysis tool with live market data), Flight Price Prediction (Random Forest on 300K+ records), Trimly (Next.js 15 + Supabase platform), and Lagom Humanizer.

OPENING RULE: You MUST open with a concrete metric or achievement — never with "I am writing to express my interest".

REQUIRED ELEMENTS in every draft:
1. Open with a HOOK: a specific result ("50+ active users", "NSRCEL finalist", "300K+ records processed")
2. Mention Drufiy AI as Founder & CEO — this differentiates him from every other applicant
3. Name 1-2 SPECIFIC projects with metrics: Markora, Flight Price Prediction, Trimly, Lagom Humanizer
4. Connect his skills DIRECTLY to what the listing asks for
5. Include: "GitHub: https://github.com/Aradhya648"
6. Sound like a driven builder/technical operator — not a generic student

ABSOLUTE RULES:
- NEVER write "I am a student at Christ University looking for an internship" without immediately following with a result
- NEVER use generic phrases like "I am passionate about", "I am excited to apply"
- Keep it under 200 words unless platform requires more
- Platform style hints below in the user message
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

    achievements = user_profile.get('achievements', [])
    profile_text = f"""
Candidate Profile:
- Name: {user_profile.get('name', 'N/A')}
- Degree: {user_profile.get('degree', 'N/A')}
- Skills: {', '.join(user_profile.get('skills', []))}
- Projects: {', '.join(user_profile.get('projects', []))}
- Experience: {user_profile.get('experience', 'N/A')}
- Achievements: {', '.join(achievements) if achievements else 'N/A'}
- GitHub: https://github.com/{user_profile.get('github', 'N/A')}
""".strip()

    listing_text = f"""
Listing Details:
- Company: {listing.company or 'Unknown'}
- Role: {listing.role or 'Unknown'}
- Platform: {listing.platform or platform}
- Description: {listing.description or 'NOT PROVIDED — infer the role requirements from the candidate\'s profile and write a highly targeted application'}
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

    achievements = user_profile.get('achievements', [])
    revision_prompt = f"""You are revising an application draft for a job/internship.

--- ORIGINAL DRAFT ---
{current_draft}
--- END ORIGINAL ---

--- USER FEEDBACK ---
{feedback}
--- END FEEDBACK ---

--- LISTING (MUST USE THESE DETAILS) ---
Company: {listing.company or 'Unknown'}
Role: {listing.role or 'Unknown'}
Description: {listing.description or 'Not provided'}
URL: {listing.url}
--- END LISTING ---

--- CANDIDATE PROFILE (MUST USE THESE SPECIFICALLY) ---
Name: {user_profile.get('name', 'N/A')}
Degree: {user_profile.get('degree', 'N/A')}
Skills: {', '.join(user_profile.get('skills', []))}
Projects (USE SPECIFIC DETAILS FROM THESE):
  • {chr(10).join('  • '.join([''] + user_profile.get('projects', [])))}
Experience: {user_profile.get('experience', 'N/A')}
Achievements:
  • {chr(10).join(['  • ' + a for a in achievements]) if achievements else '  • N/A'}
GitHub: https://github.com/{user_profile.get('github', 'N/A')}
--- END PROFILE ---

INSTRUCTIONS:
- Rewrite the draft incorporating the user's feedback
- The NEW draft MUST cite SPECIFIC metrics and outcomes from the projects above (e.g. "50+ active users", "300K+ records", "NSRCEL IIM Bangalore finalist")
- Mention Drufiy AI as Founder & CEO — this is a KEY differentiator
- Include the GitHub URL: https://github.com/Aradhya648
- Connect specific skills/projects DIRECTLY to the listing requirements
- Sound like a driven builder/operator, NOT a generic applicant
- Keep the same length as the original
- Platform: {platform}"""

    response = client.models.generate_content(
        model=gemini_config.get("model", "gemini-2.5-flash"),
        contents=revision_prompt,
        config=genai.types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.9,
            max_output_tokens=1024,
        ),
    )

    return response.text.strip()
