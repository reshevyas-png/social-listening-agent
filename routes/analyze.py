from fastapi import APIRouter, Depends, HTTPException
from schemas import AnalyzeRequest, AnalyzeResponse, PostData
from auth import verify_api_key
from scrapers.detector import detect_platform, extract_post
from agent.reply_generator import generate_reply

router = APIRouter(tags=["analyze"])


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_post(
    request: AnalyzeRequest,
    api_key: str = Depends(verify_api_key),
):
    if not request.url and not request.text:
        raise HTTPException(400, "Provide either 'url' or 'text'")

    # Step 1: Get post data
    if request.url:
        post_data = await extract_post(request.url, request.platform)
    else:
        if not request.platform:
            raise HTTPException(400, "When providing raw text, 'platform' is required")
        post_data = PostData(platform=request.platform, body=request.text)

    # Step 2: Generate reply via Claude
    result = await generate_reply(post_data)

    return AnalyzeResponse(
        skip=result["skip"],
        draft_reply=result.get("draft_reply"),
        post=post_data,
        reasoning=result.get("reasoning"),
    )
