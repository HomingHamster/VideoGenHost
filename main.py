import json
import uuid
import os
import shutil
import mimetypes
import tornado.ioloop
import tornado.web
import tornado.websocket
import tornado.escape
import random

# Dummy user database
USERS = {
    "admin": "password123"
}


# Base handler with common helpers
class BaseHandler(tornado.web.RequestHandler):
    def get_current_user(self):
        return self.get_secure_cookie("user")


# Home page – requires login
class MainHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        status = self.get_argument("status", None)
        user = tornado.escape.xhtml_escape(self.current_user.decode())
        video_list_html = self.render_video_list()
        self.render("main.html", user=user, status=status, video_list=video_list_html, xsrf_token=self.xsrf_token)

    def render_video_list(self):
        try:
            videos = os.listdir("videos")
            if not videos:
                return "<p>No videos generated yet</p>"

            items = "\n".join(
                f'<li><a href="/video/{v}">{v}</a></li>'
                for v in videos if v.endswith(".webp")
            )
            return f"<ul>{items}</ul>"
        except FileNotFoundError:
            return "<p>Video directory not found</p>"

    async def post(self):
        client = ComfyUIClient(
            server_address="127.0.0.1:8188",
            workflow_path="test.json",
            prompt=self.get_argument("prompt")
        )

        try:
            # Queue the prompt and track progress
            await client.queue_prompt()
            await client.track_progress()

            # Get generated images (including WebP videos)
            images = await client.get_images()

            # Download and save WebP videos to the "videos" folder
            await client.download_and_save_videos(images)

        finally:
            print("Workflow completed.")


# Login page
class LoginHandler(BaseHandler):
    def get(self):
        self.write("""
            <form action="/login" method="post">
                Username: <input name="username" type="text"/><br/>
                Password: <input name="password" type="password"/><br/>
                <input type="submit" value="Login"/>
            </form>
        """)

    def post(self):
        username = self.get_argument("username")
        password = self.get_argument("password")

        if USERS.get(username) == password:
            self.set_secure_cookie("user", username)
            self.redirect("/")
        else:
            self.write("Login failed. <a href='/login'>Try again</a>")


# Logout
class LogoutHandler(BaseHandler):
    def get(self):
        self.clear_cookie("user")
        self.redirect("/login")


class ComfyUIClient:
    def __init__(self, server_address, workflow_path, prompt):
        self.server_address = server_address
        self.prompt = prompt
        self.workflow = self.load_workflow(workflow_path, prompt=prompt)
        self.prompt_id = None

    @staticmethod
    def load_workflow(workflow_path, **template_vars):
        loader = tornado.template.Loader("templates")
        template = loader.load(workflow_path)
        rendered = template.generate(**template_vars,
                                     seed=random.randint(0, 2**32 - 1)).decode()
        return json.loads(rendered)

    async def queue_prompt(self):
        self.client_id = str(uuid.uuid4())
        post_data = json.dumps({
            "prompt": self.workflow,
            "client_id": self.client_id
        }).encode("utf-8")

        try:
            response = await tornado.httpclient.AsyncHTTPClient().fetch(
                f"http://{self.server_address}/prompt",
                method="POST",
                body=post_data,
                headers={"Content-Type": "application/json"}
            )
            self.prompt_id = json.loads(response.body)["prompt_id"]
            print(f" prompt id: {self.prompt_id}")
            return self.prompt_id
        except tornado.httpclient.HTTPError as e:
            print("Error queuing prompt:", e)

    async def track_progress(self):
        url = f"ws://{self.server_address}/ws?clientId={self.client_id}"
        try:
            print(f"Connecting to WebSocket at {url}...")
            connection = await tornado.websocket.websocket_connect(url)
            print("WebSocket connection established.")

            while True:
                try:
                    message = await connection.read_message()
                    if message is None:  # Server closed the connection
                        print("WebSocket connection closed by the server without error.")
                        break

                    # Print every received message for debugging
                    print(f"Received WebSocket message: {message}")

                    # Parse and handle specific message types
                    data = json.loads(message)
                    if data['type'] == 'progress':
                        current_step = data['data']['value']
                        max_steps = data['data']['max']
                        print(f"In K-Sampler -> Step: {current_step} of {max_steps}")
                    elif data['type'] == 'executing':
                        node = data['data']['node']
                        print(f"Executing node: {node}")
                    elif data['type'] == 'execution_cached':
                        cached_nodes = data['data']['nodes']
                        print(f"Cached nodes: {cached_nodes}")
                    else:
                        print(f"Unhandled message type: {data['type']}")

                except tornado.websocket.WebSocketClosedError:
                    print("WebSocketClosedError: The WebSocket connection was closed unexpectedly.")
                    break
                except Exception as e:
                    print(f"Error while processing WebSocket message: {e}")
                    break
        except tornado.websocket.WebSocketClosedError as e:
            print(f"Failed to establish WebSocket connection: {e}")
        except Exception as e:
            print(f"Unexpected error during WebSocket communication: {e}")

    async def get_images(self, save_previews=False):
        if not self.prompt_id:
            return []

        try:
            response = await tornado.httpclient.AsyncHTTPClient().fetch(
                f"http://{self.server_address}/history/{self.prompt_id}"
            )
            history = json.loads(response.body)[self.prompt_id]
            return self.process_images(history['outputs'], save_previews)
        except tornado.httpclient.HTTPError as e:
            print("Error fetching history:", e)
            return []

    def process_images(self, outputs, save_previews):
        images = []
        for node_id in outputs:
            node_output = outputs[node_id]
            if 'images' in node_output:
                for image in node_output['images']:
                    if image['type'] == 'output' or (save_previews and image['type'] == 'temp'):
                        images.append({
                            'filename': image['filename'],
                            'subfolder': image['subfolder'],
                            'type': image['type']
                        })
        return images

    async def download_and_save_videos(self, images, save_dir="videos"):
        os.makedirs(save_dir, exist_ok=True)

        for image in images:
            if image['filename'].endswith(".webp"):  # Only process WebP videos
                file_url = f"http://{self.server_address}/view?filename={image['subfolder']}/{image['filename']}"
                save_path = os.path.join(save_dir, image['filename'])

                try:
                    response = await tornado.httpclient.AsyncHTTPClient().fetch(file_url)
                    with open(save_path, "wb") as f:
                        f.write(response.body)
                    print(f"Saved video: {save_path}")
                except tornado.httpclient.HTTPError as e:
                    print(f"Error downloading {image['filename']}: {e}")


VIDEO_DIR = "videos"

class VideoStreamHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Accept-Ranges", "bytes")

    async def get(self, filename):
        filepath = os.path.join(VIDEO_DIR, filename)

        if not os.path.exists(filepath):
            raise tornado.web.HTTPError(404, f"{filename} not found")

        file_size = os.path.getsize(filepath)
        content_type, _ = mimetypes.guess_type(filepath)
        self.set_header("Content-Type", content_type or "application/octet-stream")

        range_header = self.request.headers.get("Range", None)
        if range_header:
            bytes_range = range_header.replace("bytes=", "").split("-")
            start = int(bytes_range[0])
            end = int(bytes_range[1]) if bytes_range[1] else file_size - 1
            length = end - start + 1

            self.set_status(206)
            self.set_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            self.set_header("Content-Length", str(length))

            with open(filepath, "rb") as f:
                f.seek(start)
                chunk = f.read(length)
                self.write(chunk)
        else:
            self.set_header("Content-Length", str(file_size))
            with open(filepath, "rb") as f:
                while chunk := f.read(1024 * 1024):
                    self.write(chunk)

        self.finish()


class PlayerHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("player.html", video_url="/video/sample.mp4")


def make_app():
    return tornado.web.Application([
        (r"/ws", ComfyUIClient),
        (r"/", MainHandler),
        (r"/login", LoginHandler),
        (r"/logout", LogoutHandler),
        (r"/a", PlayerHandler),
        (r"/video/(.*)", VideoStreamHandler),
        (r"/static/(.*)", tornado.web.StaticFileHandler, {"path": "static"}),
    ],
        cookie_secret="__CHANGE_THIS_SECRET__",
        login_url="/login",
        template_path="templates",
        static_path=os.path.join(os.path.dirname(__file__), "static"),
        debug=True
    )


if __name__ == "__main__":
    app = make_app()
    app.listen(8888)
    print("Server started at http://localhost:8888")
    tornado.ioloop.IOLoop.current().start()