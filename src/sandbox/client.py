import os
import uuid
import threading
import asyncio
from typing import Any
from datetime import timedelta
from opensandbox import Sandbox
from opensandbox.config import ConnectionConfig

# =========================================================================
# 【黑科技区：后台常驻事件循环】
# 解决的痛点：LangGraph 是同步执行的，但 Sandbox SDK 是异步的。
# 方案：我们在后台偷偷开一个永远不关的线程，专门用来跑异步网络请求，防止 HTTP 客户端断连。
# =========================================================================
_BACKGROUND_LOOP = None
_LOOP_THREAD = None


def get_background_loop():
    """获取或初始化后台管家线程"""
    global _BACKGROUND_LOOP, _LOOP_THREAD
    if _BACKGROUND_LOOP is None:
        _BACKGROUND_LOOP = asyncio.new_event_loop()
        # daemon=True 表示主程序退出时，这个线程也会跟着自动销毁
        _LOOP_THREAD = threading.Thread(target=_BACKGROUND_LOOP.run_forever, daemon=True)
        _LOOP_THREAD.start()
    return _BACKGROUND_LOOP


def run_async_backend(coro):
    """将一部任务安全地抛给后台管家，并在主线程原地等待结果返回"""
    loop = get_background_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()


# 全局内存字典，用来在不同节点之间暂存真实的 Sandbox 网络连接对象
_GLOBAL_SANDBOXES = {}


class LocalSandbox:
    """
    假冒官方沙箱的“替身”：
    将官方 SDK 的异步 await 方法，伪装成普通的同步 .run() 方法，专门给大模型使用。
    """

    def __init__(self, name: str, sandbox_instance):
        self.name = name
        self.sb = sandbox_instance

    def read(self, path: str) -> bytes:
        """从沙箱读取文件内容（二进制），同步包装异步 sb.files.read_bytes()"""
        print(f"[沙箱文件] 读取: {path}")

        async def _read():
            return await self.sb.files.read_bytes(path)

        return run_async_backend(_read())

    def write(self, path: str, data: str | bytes):
        """将文件内容写入沙箱，同步包装异步 sb.files.write_file()"""
        print(f"[沙箱文件] 写入: {path} ({len(data) if isinstance(data, bytes) else len(data)} bytes)")

        async def _write():
            await self.sb.files.write_file(path, data)

        run_async_backend(_write())

    def run(self, cmd: str, timeout: int = 5) -> Any:
        class RunResult:
            def __init__(self, stdout: str, stderr: str, exit_code: int):
                self.stdout = stdout
                self.stderr = stderr
                self.exit_code = exit_code

        try:
            print(f"[沙箱执行] 执行命令: {cmd}")

            # 在后台线程真实去执行命令
            async def _execute():
                return await self.sb.commands.run(cmd)

            execution = run_async_backend(_execute())

            # 兼容处理标准输出和错误
            stdout_lines = [log.text for log in execution.logs.stdout] if getattr(execution.logs, "stdout",
                                                                                  None) else []
            stderr_lines = [log.text for log in execution.logs.stderr] if getattr(execution.logs, "stderr",
                                                                                  None) else []
            return RunResult(stdout="\n".join(stdout_lines), stderr="\n".join(stderr_lines),
                             exit_code=getattr(execution, 'exit_code', 0))

        except Exception as e:
            error_msg = str(e)
            print(f"[沙箱报错] 执行期间发生异常: {error_msg}")
            # 防卡死机制：如果网络全断了，直接自爆，打断大模型的无限重试死循环
            if "All connection attempts failed" in error_msg or "ConnectError" in error_msg:
                print("\n[致命错误] 检测到沙箱已销毁或连接断开，强制终止！")
                raise RuntimeError("Sandbox connection completely lost.")
            return RunResult("", error_msg, 1)


class SandboxClient:
    def __init__(self):
        self.domain = os.getenv('SANDBOX', '127.0.0.1:8080')
        self.api_key = os.getenv('SANDBOX_API_KEY', 'my-secret-api-key-007')
        self.config = ConnectionConfig(domain=self.domain, api_key=self.api_key, use_server_proxy=True)

    def get_template(self, name: str):
        return True

    def create_template(self, name: str, image: str):
        pass

    def create_sandbox(self, template_name: str, timeout: int) -> LocalSandbox:
        sb_name = f"wsl-sandbox-{uuid.uuid4().hex[:6]}"
        print(f"\n[生命周期] 🚀 正在初始化容器: {sb_name}")

        async def _create():
            return await Sandbox.create(
                "sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com/opensandbox/code-interpreter:v1.0.2",
                connection_config=self.config,
                entrypoint=["/opt/opensandbox/code-interpreter.sh"],
                env={"PYTHON_VERSION": "3.11"},
                timeout=timedelta(seconds=timeout),
            )

        sb_instance = run_async_backend(_create())
        _GLOBAL_SANDBOXES[sb_name] = sb_instance
        return LocalSandbox(name=sb_name, sandbox_instance=sb_instance)

    def get_sandbox(self, name: str) -> LocalSandbox:
        return LocalSandbox(name=name, sandbox_instance=_GLOBAL_SANDBOXES[name])

    def delete_sandbox(self, name: str):
        sb_instance = _GLOBAL_SANDBOXES.get(name)
        if sb_instance:
            print(f"\n[生命周期] 🛑 正在清理容器实例: {name}")

            async def _kill():
                await sb_instance.kill()

            run_async_backend(_kill())
            del _GLOBAL_SANDBOXES[name]
        return True
