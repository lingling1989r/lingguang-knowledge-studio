import json, logging
LOGGER = logging.getLogger("studio.jobs")
LOGGER.setLevel(logging.INFO)
LOGGER.propagate=False
if not LOGGER.handlers:
    handler=logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    LOGGER.addHandler(handler)

def event(name, job_id=None, **fields):
    LOGGER.info(json.dumps({"event":name,"task_id":job_id,**fields},ensure_ascii=False))
