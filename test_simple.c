/* 测试文件：包含 struct/enum/switch/循环/分支结构 */

#include <stdio.h>
#include <stdint.h>
#include <string.h>

#define MAX_SIZE 64
#define ALARM_TIMEOUT 1000

typedef enum {
    IDLE = 0,
    INPUT,
    PROCESS,
    OUTPUT,
    SEND
} State;

typedef struct {
    uint32_t id;
    uint8_t state;
    uint16_t len;
} AlarmInfo;

typedef struct Node {
    struct Node* next;
    AlarmInfo data;
    uint8_t flags[8];
} Node;

static uint32_t g_counter = 0;

int status_check(uint8_t status);
void send_data(uint8_t* buf, uint16_t len);
void raise_alarm(uint32_t id);
uint16_t queue_status(void* q);

/* 简单顺序函数 */
void simple_run(void)
{
    uint8_t buf[16];
    uint16_t len = 0;
    buf[0] = 0xAA;
    len = 16;
    send_data(buf, len);
}

/* 完整分支：if/else if/else */
int process_packet(AlarmInfo* info, uint8_t* out, uint16_t maxlen)
{
    uint16_t sendLen = 0;
    int result = 0;

    if ((sendLen + info->len < maxlen) && (info->len > 0u))
    {
        send_data(out, info->len);
        sendLen += info->len;
        result = 1;
    }
    else if (info->state == PROCESS)
    {
        raise_alarm(info->id);
    }
    else
    {
        raise_alarm(ALARM_TIMEOUT);
    }

    return result;
}

/* switch 分支 */
void handle_state(State s)
{
    switch (s)
    {
        case IDLE:
            break;
        case INPUT:
            send_data((uint8_t*)"in", 2);
            break;
        case PROCESS:
            process_packet(NULL, NULL, 0);
            break;
        case OUTPUT:
            send_data((uint8_t*)"out", 3);
            break;
        default:
            raise_alarm(999);
            break;
    }
}

/* for 循环 + return */
uint16_t sum_array(uint8_t arr[], uint16_t n)
{
    uint16_t sum = 0;
    uint16_t i;
    for (i = 0; i < n; i++)
    {
        sum += arr[i];
    }
    return sum;
}

/* while 循环 + break/continue */
uint16_t count_until(uint8_t* p, uint16_t maxn)
{
    uint16_t i = 0;
    uint16_t count = 0;
    while (i < maxn)
    {
        if (p[i] == 0)
        {
            break;
        }
        if (p[i] == 0xFF)
        {
            i++;
            continue;
        }
        count++;
        i++;
    }
    return count;
}

/* do-while */
void poll_status(void* q)
{
    uint8_t st = 0;
    do
    {
        st = status_check(st);
    } while (st != 0);
}
