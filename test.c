
/**
 * @brief: 告警信息帧组装
 * @note:  帧结构:
 *           帧头2B(总长度, 小端)
 *           基础信息 19B (复用 g_boardbaseinfo)
 *           告警项 × N:
 *             长度 1B (不含自身, = 2 + raw_len)
 *             告警码 2B (大端)
 *             原始值 N B (0/1/4)
 *         写入独立告警队列, 发送前需 AlarmFrameClear()
 * @author: BlackWarrior
 * @date: 2026-07-17
 */
void ALARMDATA_DASSINFORM(void)
{
    /** 变量初始化*/
    UINT8  i = 0u;
    UINT32 offset = 0u;
    UINT8  len = 0u;
    UINT8  buf[512] = {0};
    DASS_alarm_frame_t *frame = NULL;
    
    QueueStruct* t_stpAlarmDassInformQueue = NULL;
    /** 获取DASS周期信息队列*/
    frame = AlarmFrameInfofrom();
    t_stpAlarmDassInformQueue = GetQueueAlarmDassInform();
    /** 断言检查*/
    CM_ASSERT((NULL == t_stpAlarmDassInformQueue),  __FILE__, __FUNCTION__, __LINE__);
    CM_ASSERT((NULL == frame),  __FILE__, __FUNCTION__, __LINE__);

    /*- 清空数据子系统---告警信息队列 */
    QueueClear(t_stpAlarmDassInformQueue);
	
	DASS_raise_alarm_pwlcrccheck();
    DASS_raise_alarm_fpgaresetcheck();
    DASS_raise_alarm_pwlstatecheck();

    /* 判断告警信息是否有效 */
    if (frame->item_count > 0u)
    {
        /* 开始组包 1 字节帧长度 */
        offset += 1u;

        /* 组基础信息 19B：板卡类型1 + 板卡序列号8 + 板卡位置2 + 版本信息8 */
        buf[offset] = g_boardbaseinfo.board_type;
        offset += 1;

        CM_Memcpy(&buf[offset], 8, g_boardbaseinfo.boardsn, 8);
        offset += 8;

        CM_ShortToChar(g_boardbaseinfo.boardposition, &buf[offset]);
        offset += 2;

        CM_Memcpy(&buf[offset], 4, g_boardbaseinfo.t_Integrationver, 4);
        offset += 4;

        CM_Memcpy(&buf[offset], 4, g_boardbaseinfo.t_FPGAver, 4);
        offset += 4;

        /* 遍历组告警信息字段*/
        for (i = 0; i < frame->item_count; i++)
        {
            /* 组单条告警信息 */
            len = 2u + frame->raw_len[i];
            buf[offset] = len;
            offset += 1;

            CM_ShortToChar(frame->alarm_code[i], &buf[offset]);
            offset += 2;

            /* 若改字段有原始值 */
            if (frame->raw_len[i] > 0u)
            {
                /* 组原始值 */
                CM_Memcpy(&buf[offset], frame->raw_len[i],
                          frame->raw_val[i], frame->raw_len[i]);
                offset += frame->raw_len[i];
            }
        }
        /** 写入队列 */
        buf[0] = offset - 1u;
        
        (void)QueueWrite(offset, buf, t_stpAlarmDassInformQueue);

    }

    /*- 清空告警信息 */
    AlarmFrameClear();
}
/**
 * @brief: ATP汇总周期状态信息
 * @param {UINT8*} sendBuf，数据发送缓存，非空指针
 * @param {UINT16} maxlen，数据发送缓存最大长度，0-0xFFFF
 * @return {UINT16} sendLen，实际写入数据长度，0-0xFFFF
 * @author: BlackWarrior
 * @date: 2026-08-05 15:13:11
 */
UINT16 AtpGetCycleDassInfor(UINT8* sendBuf, UINT16 maxlen)
{
    /** 变量初始化 */
    UINT16 sendLen = 0x0;
    UINT16 t_u16I = 0x0;
    UINT16 datalen = 0x0;
    STU_PwlRcv_DassInfor* pwlRcvCycleDassPacket = NULL;
    QueueStruct* t_stpDassInformQueue = NULL;
    UINT8* tempPtr = NULL;
    UINT16 tempCrc = 0x0;
    /** 对参数断言检查 */
    CM_ASSERT((NULL == sendBuf), __FILE__, __FUNCTION__, __LINE__);

    pwlRcvCycleDassPacket = PLFM_PwlRcvCycleDassPacket();
    t_stpDassInformQueue = GetQueueCycleDassInform();

    /** 获取主机板数据子系统周期状态信息*/
    datalen = (UINT16)QueueStatus(t_stpDassInformQueue);
    /*- 判断是否可以写入主机板信息 */
    if((sendLen + datalen < maxlen) && (datalen > 0u))
    {
        /*- 写入主机板周期状态信息 */
        (void)QueueRead((UINT32)datalen, &sendBuf[sendLen], t_stpDassInformQueue);
        sendLen += datalen;
    }
    else
    {
        /**空 */;
    }


    /** 遍历获取其他执行板卡数据子系统周期状态信息*/
    for(t_u16I = 0x0; t_u16I < DASSBOARD_MAX_NUM; t_u16I++)
    {
        /** 获取执行板卡的周期状态信息长度 */
        datalen = pwlRcvCycleDassPacket->BoardPacket[t_u16I].rcvlen;
        /*- 判断剩余空间是否满足写入 */
        if((sendLen + datalen < DASSSEND_MAX_LEN) && (datalen > 0u))
        {
            /*- 写入状态信息，并获取实际写入长度 */
            tempPtr = pwlRcvCycleDassPacket->BoardPacket[t_u16I].rcvdata;
            CM_Memcpy(&sendBuf[sendLen], (DASSSEND_MAX_LEN - sendLen), tempPtr, datalen);
            sendLen += datalen;

            DarkLogPrint(ENUM_LOG_PROMPT, &t_u16I, LOGTYPE_GETBOARD_DASSINDEX, 2);
            DarkLogPrint(ENUM_LOG_PROMPT, &datalen, LOGTYPE_GETBOARD_DASSLEN, 2);
        }
        else
        {
            ;
        }
    }
    /**返回实际写入的数据长度 */
    return sendLen;
}