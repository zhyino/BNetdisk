\
        # app/app.py
        from flask import Flask, render_template, request, jsonify, Response
        from backup import worker
        import json

        app = Flask(__name__, template_folder="templates", static_folder="static")

        @app.route("/")
        def index():
            return render_template("index.html")

        @app.route("/api/add", methods=["POST"])
        def add_task():
            data = request.get_json(force=True)
            src = data.get("src", "").strip()
            dest = data.get("dest", "").strip()
            filter_images = bool(data.get("filter_images", True))
            filter_nfo = bool(data.get("filter_nfo", True))
            if not src or not dest:
                return jsonify({"ok": False, "error": "src and dest required"}), 400
            worker.add_task(src, dest, filter_images=filter_images, filter_nfo=filter_nfo)
            return jsonify({"ok": True})

        @app.route("/api/queue", methods=["GET"])
        def get_queue():
            q = worker.task_queue
            items = []
            with q.mutex:
                for item in list(q.queue):
                    items.append({
                        "src": item.get("src"),
                        "dest": item.get("dest"),
                        "filter_images": item.get("filter_images"),
                        "filter_nfo": item.get("filter_nfo")
                    })
            return jsonify({"queue": items})

        @app.route("/stream")
        def stream():
            def gen(client_q):
                try:
                    while True:
                        msg = client_q.get()
                        yield f"data: {msg}\\n\\n"
                finally:
                    worker.unregister_client(client_q)
            client_q = worker.register_client()
            return Response(gen(client_q), mimetype="text/event-stream")

        if __name__ == "__main__":
            app.run(host="0.0.0.0", port=8000, threaded=True)
