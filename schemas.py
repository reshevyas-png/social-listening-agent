from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional


class Platform(str, Enum):
    reddit = "reddit"
    twitter = "twitter"
    linkedin = "linkedin"


class AnalyzeRequest(BaseModel):
    url: Optional[str] = Field(None, description="URL of the social media post")
    text: Optional[str] = Field(
        None, description="Raw post text if URL not provided"
    )
    platform: Optional[Platform] = Field(
        None, description="Force platform; auto-detected from URL if omitted"
    )


class PostData(BaseModel):
    platform: Platform
    author: Optional[str] = None
    title: Optional[str] = None
    body: str
    subreddit: Optional[str] = None
    url: Optional[str] = None


class AnalyzeResponse(BaseModel):
    skip: bool = Field(description="True if this post is not a match for our tool")
    draft_reply: Optional[str] = Field(
        None, description="The generated reply, null if skip=true"
    )
    post: PostData = Field(description="The parsed post data")
    reasoning: Optional[str] = Field(
        None, description="Why the agent chose to reply or skip"
    )
