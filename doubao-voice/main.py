# Patch gevent before anything imports ssl. The dify_plugin SDK patches on its
# own import, but by then ssl may already be imported by the daemon bootstrap,
# which triggers RecursionError on Python 3.12 when establishing TLS connections
# (e.g. speech2text HTTPS calls). Patching here, as the very first statement,
# ensures gevent monkey-patches ssl before it is imported.
from gevent import monkey

monkey.patch_all()

from dify_plugin import DifyPluginEnv, Plugin

plugin = Plugin(DifyPluginEnv(MAX_REQUEST_TIMEOUT=120))

if __name__ == "__main__":
    plugin.run()
