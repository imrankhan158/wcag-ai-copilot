from fastapi import APIRouter

router = APIRouter()

@router.get("", summary="Health Check", description="Check the health status of the WCAG AI Copilot service.")
def health_check():
    return {
        "status": "healthy",
        "service": "wcag-ai-copilot"
    }