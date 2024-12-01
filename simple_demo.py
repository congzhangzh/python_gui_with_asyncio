# TODO: this just for linux, MAC & Windows should be different

import tkinter as tk
import asyncio
import uvloop
import threading
import select
import tracemalloc
import os

#PEP idea
# Loop implment side
    # loop.check_event
    # loop.run_once
    # loop.process_ready
# gui event loop side
    # process loop ready micro task in every event loop tick

os.environ['PYTHONASYNCIODEBUG'] = '1'

class ProcessReadyManager:
    _instance = None
    
    def __init__(self):
        self.loop = None
        self.root = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = ProcessReadyManager()
        return cls._instance
    
    def set_loop(self, loop):
        self.loop = loop
        return self
    
    def set_root(self, root):
        self.root = root
        return self

    # be careful, the only way to do it is do it in the event loop, but not a callback!
    # it's just workaround here
    def ensure_process_ready(self, func):
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            
            current_loop = self.loop or asyncio.get_event_loop()
            current_root = self.root
            
            if current_root:
                def process_ready():
                    #current_loop.call_soon(current_loop._run_once)
                    current_loop.process_ready()
                current_root.after(0, process_ready)
            return result
        return wrapper

# 使用示例
process_ready_mgr = ProcessReadyManager.get_instance()

# ---- Tkinter 部分 ----
def create_tk_app():
    root = tk.Tk()
    root.title("Simple Demo")
    root.geometry("300x200")
    
    label = tk.Label(root, text="Status: Ready")
    label.pack(pady=20)
    
    button = tk.Button(root, text="Click Me", command=lambda: tk_after_test("from button"))
    button.pack(pady=20)
    
    return root, label, button

def run_tk(root):
    #asyncio.ensure_future(dummy_task())
    asyncio.get_event_loop().create_task(dummy_task())
    root.mainloop()

# ---- Asyncio 部分 ----
async def dummy_task(context="default"):
    print(f"Starting async task... {context}")
    for i in range(3):
        print(f"Async task step {(i+1)*3}")
        await asyncio.sleep(3)
    print("Async task completed!")

async def run_async():
    #uvloop.install()
    await dummy_task()

@process_ready_mgr.ensure_process_ready
def tk_after_test(context):
    l=asyncio.get_event_loop()
    l.create_task(dummy_task(context))
    print(f"tk after test: {context}")

# ---- Main ----
def main():
    tracemalloc.start()
    # 创建 TK 应用
    root, label, button = create_tk_app()
    
    # 选择运行模式 (取消注释其中之一)
    
    # 模式1: 只运行 TK
    # run_tk(root)
    
    # 模式2: 只运行 Async
    #asyncio.run(run_async())
    
    # 模式3: 都运行（注意：这只是示例，实际上这样运行会阻塞）
    #asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    loop = uvloop.Loop()
    loop.set_debug(True)
    #get backend id first
    #loop._get_backend_id()
    #run event loop 

    asyncio.set_event_loop(loop)
    #asyncio._set_running_loop(loop) #?

    #loop.run_once()
    #root.after(0, loop.run_until_complete, run_async())
    #loop.run_until_complete(run_async())
    #asyncio.run(run_async())
    root.after(0, tk_after_test, "from ui thread")

    process_ready_mgr = ProcessReadyManager.get_instance()
    process_ready_mgr.set_loop(loop)
    process_ready_mgr.set_root(root)
    
    prepare_backend_thread(root, loop)

    run_tk(root)
    #loop.set_running(False) # TODO: safe way to stop & join?

async def dummy_task_for_trigger():
    '''
    dummy task for trigger, as uvloop does not expose uv_run? a issue to uvloop?
    '''
    print("--begin-- dummy_task_for_trigger")
    # 使用 socket 或 pipe 立即产生信号
    r, w = await asyncio.open_connection('127.0.0.1', 8888)

    await asyncio.sleep(1)
    print("--end-- dummy_task_for_trigger")

def prepare_backend_thread(tk_root, loop):
    # 创建信号量用于线程协调
    sem = threading.Semaphore(0)
    # 获取后端文件描述符
    backend_id = loop._get_backend_id()
    print(f"backend id: {backend_id}")
    
    # 创建epoll实例
    epoll = select.epoll()
    epoll.register(backend_id, select.POLLIN)
        
    def run_events_on_ui_thread():
        # 在UI线程中运行事件循环
        #loop.run_once()  # 运行当前所有可用事件
        #loop.run_until_complete(dummy_task_for_trigger())
        #loop.call_soon(dummy_task_for_trigger)
        #loop.run_forever()
        loop.run_once()
        #asyncio.ensure_future(dummy_task("from ui thread"))
        sem.release()  # 通知后端线程可以继续轮询
        #print("sem released")
    
    def run_loop_once():
        run_events_on_ui_thread()
        pass

    def backend_thread_loop():
        try:
            while True:  # 持续监听事件
                sem.acquire()
                #print("sem acquired")
                # 等待事件
                #events = epoll.poll(timeout=0.1)  # 1秒超时
                while True:
                    try:
                        events = epoll.poll()
                        break  # 成功获取事件，退出内部循环
                    except InterruptedError:  # EINTR
                        continue  # 重试

                # tk_root.after(0, run_events_on_ui_thread)
                if events:
                    print(f"events: {events}")
                    # 在UI线程中调度事件处理
                    tk_root.after(0, run_events_on_ui_thread)
                    # 等待UI线程处理完成
                else:
                    raise Exception("should always has events, or can not acquire semaphore again!")
                    pass
        except Exception as e:
            print(f"Backend thread error: {e}")
        finally:
            epoll.unregister(backend_id)
            epoll.close()

    run_loop_once()
    #loop.set_running(True)
    #loop.create_task(dummy_task_for_trigger())
    #loop.create_task(asyncio.sleep(1))
    #loop.create_task(asyncio.sleep(3))
    #loop.create_task(loop.(3))
    #loop.call_soon(lambda: print("call soon"))
    #run_loop_once()
    #loop.set_running(True)
    threading.Thread(target=backend_thread_loop, daemon=True).start()

if __name__ == "__main__":
    main() 
