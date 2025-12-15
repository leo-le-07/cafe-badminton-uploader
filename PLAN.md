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
- Loop through each workspace created in Stage 1.
- Fast-Selection GUI: Opens an instant-loading window displaying candidate frames for the current video.
- Human Decision: User cycles candidates (A/D keys) and locks in the best frame (Enter) or defaults to the middle frame (S/Q).
- Outcome: The script automatically saves the chosen image as selected.jpg in the {video_name} folder, ready for final rendering.

### Stage 3: Thumbnail rendering
Step 1: Load Assets Read the metadata.json file to get the team names and tournament info. Load the selected.jpg image chosen in Stage 2 and load the custom fonts (e.g., Montserrat) from your assets folder.

Step 2: Enhance Image Apply a color boost to the raw frame to make the players stand out. Add a subtle vignette (darkened corners) to focus the viewer's eye on the center action.

Step 3: Draw Background Bar Create a semi-transparent dark bar at the bottom of the image. This "lower third" graphic ensures the text remains readable regardless of the court floor color.

Step 4: Render Typography Calculate the optimal font size so long names fit perfectly within the width. Draw the match details (Teams) in large white text and the context (Tournament/Round) in smaller accent-colored text (Gold/Yellow) with drop shadows.

Step 5: Export Final Combine all layers and save the high-quality result as thumbnail_final.jpg in the video's folder.

### Stage 3: Autonomous Upload (Bot Only)
* **Trigger:** User runs `run_upload.py`.
* **Loop:** The script iterates through approved workspaces.
    1.  **Upload:** Pushes video and generated thumbnail to YouTube using `metadata.json`.
    2.  **Cleanup:** Moves the original video to "Completed" and archives/deletes the workspace.
