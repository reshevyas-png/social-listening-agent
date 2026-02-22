from abc import ABC, abstractmethod
from schemas import PostData


class BaseScraper(ABC):
    @abstractmethod
    async def scrape(self, url: str) -> PostData:
        pass
