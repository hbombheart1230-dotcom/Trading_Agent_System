from libs.catalog.api_catalog import ApiCatalog
from libs.catalog.api_discovery import ApiDiscovery
from libs.catalog.api_planner import ApiPlanner
from libs.core.event_logger import EventLogger


def plan_api(query: str, catalog_path: str):
    logger = EventLogger(node="plan_api")
    logger.start({"query": query})

    catalog = ApiCatalog.load(catalog_path)
    discovery = ApiDiscovery(catalog)
    planner = ApiPlanner()

    matches = discovery.search(query, top_k=5)
    result = planner.plan(matches)

    logger.end({"action": result.action})
    return result