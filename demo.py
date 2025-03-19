import sys

FRE_PER_SLICING = 1800  # 处理频率，每个时间片处理 1800 次
MAX_DISK_NUM = (10 + 1)  # 最大磁盘数量，假设最多 10 个磁盘，多加 1 方便索引（从 1 开始）
MAX_DISK_SIZE = (16384 + 1)  # 每个磁盘的存储单元数（16,384）
MAX_REQUEST_NUM = (30000000 + 1)  # 最大请求数量（3,000 万 + 1）
MAX_OBJECT_NUM = (100000 + 1)  # 最多可以存储的对象数量（10 万 + 1）
REP_NUM = 3  # 每个对象的副本数
EXTRA_TIME = 105  # 额外的时间片

disk = [[0 for _ in range(MAX_DISK_SIZE)] for _ in range(MAX_DISK_NUM)]  # 磁盘的数据结构，[磁盘数， 单元数]
disk_point = [0 for _ in range(MAX_DISK_NUM)]  # [磁盘数]
_id = [0 for _ in range(MAX_OBJECT_NUM)]  # 存储的ID数，[最大object数量]

current_request = 0
current_phase = 0


class Object:
    def __init__(self):
        self.replica = [0 for _ in range(REP_NUM + 1)]
        self.unit = [[] for _ in range(REP_NUM + 1)]
        self.size = 0
        self.lastRequestPoint = 0
        self.isDelete = False


req_object_ids = [0] * MAX_REQUEST_NUM  # 请求i访问的object id
req_prev_ids = [0] * MAX_REQUEST_NUM  # 请求i之前访问的请求id
req_is_dones = [False] * MAX_REQUEST_NUM  # 请求i是否完成

objects = [Object() for _ in range(MAX_OBJECT_NUM)]  # [最大object数]


def do_object_delete(object_unit, disk_unit, size):
    for i in range(1, size + 1):
        disk_unit[object_unit[i]] = 0  # 把涉及到的内存清掉


def timestamp_action():
    timestamp = input().split()[1]
    print(f"TIMESTAMP {timestamp}")
    sys.stdout.flush()


def delete_action():
    n_delete = int(input())
    abortNum = 0
    for i in range(1, n_delete + 1):
        _id[i] = int(input())  # 需要删除的对象，shape是max_object_num(100000)
    for i in range(1, n_delete + 1):
        delete_id = _id[i]
        currentId = objects[delete_id].lastRequestPoint  # 上一个访问的request_id
        while currentId != 0:
            if not req_is_dones[currentId]:  # 判断这个上个请求是否完成了
                abortNum += 1  # 统计未完成的请求数
            currentId = req_prev_ids[currentId]  # 继续追溯之前的请求

    print(f"{abortNum}")
    for i in range(n_delete + 1):
        delete_id = _id[i]
        currentId = objects[delete_id].lastRequestPoint
        while currentId != 0:
            if not req_is_dones[currentId]:
                print(f"{currentId}")
            currentId = req_prev_ids[currentId]  # 这里往上的部分和上面是一样的
        for j in range(1, REP_NUM + 1):  # 删除所有的副本
            do_object_delete(objects[delete_id].unit[j], disk[objects[delete_id].replica[j]], objects[delete_id].size)
        objects[delete_id].isDelete = True  # 标注已经删除
    sys.stdout.flush()


def do_object_write(object_unit, disk_unit, size, object_id):
    current_write_point = 0
    for i in range(1, V + 1):  # V是一个磁盘的单元数，size是几，就写几次object的id
        if disk_unit[i] == 0:
            disk_unit[i] = object_id  # 把object的id写在硬盘空的地方
            current_write_point += 1  # 写的位置后移
            object_unit[current_write_point] = i  # 第一个是空着的，一定是0，写的时候直接跳过第一个了，记的是object的分别写在哪些单元
            if current_write_point == size:
                break
    assert (current_write_point == size)


def write_action():
    n_write = int(input())
    for i in range(1, n_write + 1):  # 这个for是遍历要写入的数据个数，i的单位是object
        write_input = input().split()
        write_id = int(write_input[0])
        size = int(write_input[1])
        objects[write_id].lastRequestPoint = 0  # 最后一个请求的id初始化成0，因为request的id是从1开始的，所以0就是初始化
        for j in range(1, REP_NUM + 1):  # 这个for是副本
            objects[write_id].replica[j] = (write_id + j) % N + 1  # 这个副本写在哪个硬盘上
            objects[write_id].unit[j] = [0 for _ in range(size + 1)]  # 这个副本在硬盘的哪个单元，但是是从索引1开始计的，shape是size+1
            objects[write_id].size = size
            objects[write_id].isDelete = False
            do_object_write(objects[write_id].unit[j], disk[objects[write_id].replica[j]], size, write_id)  # 具体的写入，在此之前都是初始化的
        print(f"{write_id}")
        for j in range(1, REP_NUM + 1):
            print_next(f"{objects[write_id].replica[j]}")
            for k in range(1, size + 1):
                print_next(f" {objects[write_id].unit[j][k]}")
            print()
    sys.stdout.flush()


def read_action():
    request_id = 0
    nRead = int(input())
    for i in range(1, nRead + 1):  # for读取的次数
        read_input = input().split()
        request_id = int(read_input[0])
        objectId = int(read_input[1])
        req_object_ids[request_id] = objectId  # 请求的序列，比较和请求id对应的object id
        req_prev_ids[request_id] = objects[objectId].lastRequestPoint  # 上一个请求序列，如果没有的话默认是0
        objects[objectId].lastRequestPoint = request_id
        req_is_dones[request_id] = False  # request是否完成
    global current_request
    global current_phase
    if current_request == 0 and nRead > 0:  # 如果有读的需求，且是第一次读
        current_request = request_id  # 设置当前request id，如果有多个读，只算最后一个？
    if current_request == 0:  # 没有需求，直接输出n个#说明所有磁头都没操作
        for i in range(1, N + 1):
            print("#")
        print("0")
    else:
        current_phase += 1
        objectId = req_object_ids[current_request]
        for i in range(1, N + 1):  # 遍历每个硬盘
            if i == objects[objectId].replica[1]:  # 看这个object的本体数据存在哪里
                if current_phase % 2 == 1:  # 如果是奇数
                    print(f"j {objects[objectId].unit[1][int(current_phase / 2 + 1)]}")  # j表示跳跃，跳到对应单元
                    # current_phase是1的话，其实就是跳到起始地址的那个单元位置
                else:
                    print("r#")
            # 其中'p'字符代表"Pass"动作，'r'字符代表"Read"动作。运动结束用字符'#'表示。 相当于比如有两个连续单元要读取就是rr
            else:
                print("#")
        if current_phase == objects[objectId].size * 2:  # 他这个逻辑似乎是跳一下读一下，和例子不太一样
            if objects[objectId].isDelete:  # 如果这个对象被删掉了
                print("0")
            else:
                print(f"1\n{current_request}")  # 读到了
                req_is_dones[current_request] = True
            current_request = 0
            current_phase = 0
        else:
            print("0")  # 没有读到
    sys.stdout.flush()


def print_next(message):
    print(f"{message}", end="")


if __name__ == '__main__':
    user_input = input().split()
    T = int(user_input[0])  #
    M = int(user_input[1])  # 标签数量
    N = int(user_input[2])  # 磁盘数量
    V = int(user_input[3])  # 每个磁盘的单元数
    G = int(user_input[4])  # 每个磁头最多读取的token数
    # skip preprocessing
    for item in range(1, M * 3 + 1):
        input()
    print("OK")
    sys.stdout.flush()
    for item in range(1, N + 1):
        disk_point[item] = 1
    for item in range(1, T + EXTRA_TIME + 1):
        timestamp_action()
        delete_action()
        write_action()
        read_action()
