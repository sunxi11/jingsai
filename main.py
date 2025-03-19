"""
分布式存储系统（完整I/O交互版）
严格保持与问题描述一致的输入输出格式
"""
import sys
import heapq
from collections import defaultdict

# region 系统常量
MAX_DISK_NUM = 11  # 磁盘数量上限(1-based)
MAX_DISK_SIZE = 16385  # 单盘存储单元数
REP_NUM = 3  # 副本数
EXTRA_TIME = 105  # 额外处理时间片


# endregion

# region 数据结构
class DiskState:
    def __init__(self, disk_id, V):
        self.disk_id = disk_id
        self.position = 1
        self.free_blocks = []
        self.allocated = defaultdict(list)  # {obj_id: [(start, end)]}
        heapq.heappush(self.free_blocks, (V, 1, V))

    def allocate(self, size):
        """空间分配（返回分配结果字符串）"""
        if not self.free_blocks:
            return ""

        block = heapq.heappop(self.free_blocks)
        if block[0] < size:
            return ""

        alloc_start = block[1]
        alloc_end = alloc_start + size - 1
        if alloc_end < block[2]:
            heapq.heappush(self.free_blocks,
                           (block[2] - alloc_end, alloc_end + 1, block[2]))

        return f"{alloc_start} " + " ".join(map(str, range(alloc_start, alloc_end + 1)))


class StorageObject:
    def __init__(self):
        self.replicas = []  # [(disk_id, [positions])]
        self.size = 0
        self.last_request = 0
        self.is_deleted = False


class Request:
    def __init__(self, req_id, obj_id):
        self.req_id = req_id
        self.obj_id = obj_id
        self.actions = []  # 当前磁盘的动作队列
        self.current_disk = 0  # 当前操作的磁盘


# endregion
# region 存储控制器
class StorageSystem:
    def __init__(self, N, V, G):
        self.N = N
        self.V = V
        self.G = G
        self.disks = {i: DiskState(i, V) for i in range(1, N + 1)}
        self.objects = {}
        self.requests = {}
        self.pending_requests = []


    # region 删除处理
    def process_deletes(self, delete_ids):
        aborted = []
        for obj_id in delete_ids:
            if obj_id not in self.objects:
                continue

            obj = self.objects[obj_id]
            req_id = obj.last_request
            while req_id != 0:
                if not self.requests[req_id]['done']:
                    aborted.append(req_id)
                req_id = self.requests[req_id]['prev']

            # 释放磁盘空间
            for disk_id, pos_list in obj.replicas:
                disk = self.disks[disk_id]
                start = pos_list[0]
                end = pos_list[-1]
                heapq.heappush(disk.free_blocks, (end - start + 1, start, end))

            del self.objects[obj_id]

        return aborted

    # endregion

    # region 写入处理
    def process_writes(self, write_ops):
        results = []
        for op in write_ops:
            obj_id, size, _ = op
            replicas = []

            # 选择三个磁盘（简化策略）
            selected_disks = heapq.nsmallest(3, self.disks.values(),
                                             key=lambda d: len(d.free_blocks))

            # 分配空间
            for disk in selected_disks:
                alloc_str = disk.allocate(size)
                if not alloc_str:
                    return []
                positions = list(map(int, alloc_str.split()))
                replicas.append((disk.disk_id, positions))

            # 记录对象
            self.objects[obj_id] = StorageObject()
            self.objects[obj_id].replicas = replicas
            self.objects[obj_id].size = size

            # 生成输出
            results.append({
                'obj_id': obj_id,
                'replicas': replicas
            })

        return results

    # endregion

    # region 读取处理
    def process_reads(self, read_ops, current_time):
        # 生成磁头调度计划
        schedule = {i: [] for i in range(1, self.N + 1)}
        completed = []

        for req_id, obj_id in read_ops:
            if obj_id not in self.objects:
                continue

            obj = self.objects[obj_id]
            self.requests[req_id] = {
                'obj_id': obj_id,
                'phases': obj.size * 2,
                'current_phase': 0,
                'done': False,
                'prev': obj.last_request
            }
            obj.last_request = req_id

            # 选择最优副本
            best_disk = min(obj.replicas,
                            key=lambda r: self.calculate_cost(r[0], r[1]))
            disk_id, positions = best_disk

            # 生成动作序列
            actions = self.generate_actions(disk_id, positions)
            self.requests[req_id]['actions'] = actions
            schedule[disk_id].append(req_id)

        # 分配令牌
        remaining_G = self.G
        for disk_id in schedule:
            disk = self.disks[disk_id]
            req_queue = schedule[disk_id]

            while remaining_G > 0 and req_queue:
                req_id = req_queue.pop(0)
                req = self.requests[req_id]

                while remaining_G > 0 and req['current_phase'] < req['phases']:
                    action, cost = self.get_next_action(disk, req)
                    if cost > remaining_G:
                        break

                    schedule[disk_id].append(action)
                    remaining_G -= cost
                    req['current_phase'] += 1

                if req['current_phase'] >= req['phases']:
                    req['done'] = True
                    completed.append(req_id)

        return schedule, completed

    def calculate_cost(self, disk_id, positions):
        """计算移动到目标位置的令牌消耗"""
        current = self.disks[disk_id].position
        target = positions[0]
        steps = (target - current) % self.V
        return min(steps * 1 + 64, 128 + 64)

    def generate_actions(self, disk_id, positions):
        """生成动作序列（兼容原输出格式）"""
        actions = []
        current = self.disks[disk_id].position

        for pos in positions:
            steps = (pos - current) % self.V
            if steps > 0:
                if steps * 1 + 64 <= 128 + 64:
                    actions.extend(['p'] * steps)
                else:
                    actions.append(f'j {pos}')
                current = pos
            actions.append('r')

        return actions
    # endregion


# endregion

# region 系统接口
def main():
    # 读取输入参数
    T, M, N, V, G = map(int, sys.stdin.readline().split())

    # 跳过预处理数据
    for _ in range(M * 3):
        sys.stdin.readline()

    print("OK")
    sys.stdout.flush()

    system = StorageSystem(N, V, G)

    # 处理每个时间片
    for _ in range(T + EXTRA_TIME):
        # 读取时间片头
        timestamp = input().split()[1]
        print(f"TIMESTAMP {timestamp}")
        sys.stdout.flush()

        # 处理删除
        n_delete = int(sys.stdin.readline())
        delete_ids = [int(sys.stdin.readline()) for _ in range(n_delete)]
        aborted = system.process_deletes(delete_ids)

        # 输出删除结果
        print(len(aborted))
        if aborted:
            print(" ".join(map(str, aborted)))
        else:
            pass
        sys.stdout.flush()

        # 处理写入
        n_write = int(sys.stdin.readline())
        write_ops = []
        for _ in range(n_write):
            parts = sys.stdin.readline().split()
            write_ops.append((int(parts[0]), int(parts[1]), int(parts[2])))

        write_results = system.process_writes(write_ops)

        # 输出写入结果
        print(n_write)
        for res in write_results:
            print(res['obj_id'])
            for disk_id, positions in res['replicas']:
                print(f"{disk_id} {' '.join(map(str, positions))}")
        sys.stdout.flush()

        # 处理读取
        n_read = int(sys.stdin.readline())
        read_ops = []
        for _ in range(n_read):
            req_id, obj_id = map(int, sys.stdin.readline().split())
            read_ops.append((req_id, obj_id))

        schedule, completed = system.process_reads(read_ops, _)

        # 输出读取调度
        for disk_id in range(1, N + 1):
            actions = schedule.get(disk_id, [])
            if not actions:
                print("#")
            else:
                print(" ".join(actions))
        print(len(completed))
        if completed:
            print(" ".join(map(str, completed)))
        else:
            print()
        sys.stdout.flush()


if __name__ == "__main__":
    main()
# endregion
