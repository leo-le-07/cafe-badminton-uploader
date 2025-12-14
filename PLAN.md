# Project Plan: Badminton Match Automated Uploader
The workflow is now split into **Batch Creation** and **Human Review** to maximize efficiency.

### Stage 1: The Batch Job (Machine Only)
* **Trigger:** User runs `run_batch.py`.
* **Loop:** The script iterates through every `.mov` in the input folder.
    1.  **Workspace Creation:** Creates a dedicated folder `{video_name}/`.
    2.  **Metadata Parsing:** Parses the filename and saves data to `metadata.json` in that folder.
    3.  **Extraction:** Extracts 5 candidate frames and saves them to `{video_name}/candidates/`.
* **Outcome:** A structured `{video_name}` directory containing organized assets for every video.

### Stage 2: The Review & Polish (Human-in-the-Loop)
* **Trigger:** User opens the `_processing` folder in their OS (Finder/Explorer).
* **Action:** User checks the `candidates` folder for each match and selects the winner (Method: Rename or Drag to Root).
* **Process:** User runs `run_render.py`. The script finds the selected image, applies text/color grading, and saves the final thumbnail.

### Stage 3: Autonomous Upload (Bot Only)
* **Trigger:** User runs `run_upload.py`.
* **Loop:** The script iterates through approved workspaces.
    1.  **Upload:** Pushes video and generated thumbnail to YouTube using `metadata.json`.
    2.  **Cleanup:** Moves the original video to "Completed" and archives/deletes the workspace.
