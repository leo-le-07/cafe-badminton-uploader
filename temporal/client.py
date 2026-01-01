from dataclasses import dataclass
from constants import TEMPORAL_TASK_QUEUE
from pathlib import Path
import config
from temporalio.client import Client
from datetime import datetime


@dataclass
class VideoWorkflowOptions:
    video_path: str
    top_n: int = config.TOP_RANKED_CANDIDATES_NUM


async def get_client():
    client = await Client.connect(config.TEMPORAL_SERVER_ADDRESS)

    return client


def gen_workflow_id(video_path: Path) -> str:
    video_name = video_path.stem
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{video_name}_{timestamp}"


async def start_video_workflow(client: Client, options: VideoWorkflowOptions):
    workflow_id = gen_workflow_id(Path(options.video_path))
    return await client.execute_workflow(
        "ProcessVideoWorkflow",
        options.video_path,
        id=workflow_id,
        task_queue=TEMPORAL_TASK_QUEUE,
    )
