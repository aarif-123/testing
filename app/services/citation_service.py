import datetime
from typing import List, Dict, Optional

class CitationService:
    @staticmethod
    def to_bibtex(papers: List[Dict]) -> str:
        """Convert a list of paper metadata to BibTeX format."""
        bib_entries = []
        for p in papers:
            title = p.get("title", "Untitled")
            authors = p.get("authors", [])
            author_str = " and ".join(authors) if isinstance(authors, list) else str(authors)
            year = p.get("year", datetime.datetime.now().year)
            
            # Generate a unique key
            last_name = authors[0].split()[-1] if authors else "Unknown"
            clean_title = "".join(filter(str.isalnum, title[:10]))
            bib_key = f"{last_name}{year}{clean_title}".lower()
            
            entry = f"""@article{{{bib_key},
  title = {{{title}}},
  author = {{{author_str}}},
  year = {{{year}}},
  journal = {{{p.get('venue', 'arXiv Preprint')}}},
  url = {{{p.get('url', '')}}},
  abstract = {{{p.get('abstract', '')}}}
}}"""
            bib_entries.append(entry)
            
        return "\n\n".join(bib_entries)

    @staticmethod
    def to_apa(papers: List[Dict]) -> str:
        """Convert a list of paper metadata to APA style citations."""
        apa_entries = []
        for p in papers:
            title = p.get("title", "Untitled")
            authors = p.get("authors", [])
            if isinstance(authors, list):
                if len(authors) > 7:
                    authors_str = ", ".join(authors[:6]) + ", ... " + authors[-1]
                elif len(authors) > 1:
                    authors_str = ", ".join(authors[:-1]) + ", & " + authors[-1]
                elif authors:
                    authors_str = authors[0]
                else:
                    authors_str = "Unknown"
            else:
                authors_str = str(authors)
                
            year = p.get("year", "n.d.")
            venue = p.get("venue", "arXiv")
            
            entry = f"{authors_str} ({year}). {title}. {venue}."
            if p.get('url'):
                entry += f" {p['url']}"
            apa_entries.append(entry)
            
        return "\n\n".join(apa_entries)

citation_service = CitationService()
