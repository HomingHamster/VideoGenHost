VideoGenHost
============

This repo will allow you to generate short clips using a ComfyUI
instance running locally. It allows you to provide only the prompt,
and get a video file downloaded to the folder this app is running in.
It will also poll for completion, host the video files and provide
a player with buffering.

TODO
----
* Progress reporting beyond pending/completed.
* HTTPS server

Install
-------
1. Follow the ComfyUI install process separately to this app,
and have a running ComfyUI instance.
2. Create a venv for this project.
3. Activate the venv.
4. Install the requirements from the requirements file into the venv.
5. Run the main.py file and your server will be avialable on 
http://localhost:8888