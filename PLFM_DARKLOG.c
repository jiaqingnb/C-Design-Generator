/*
 * PLFM_DARKLOG.c
 *
 *  Created on: 2022年4月19日
 *      Author: master
 */

#include "PLFM_DARKLOG.h"
#include "PLFM_LOG_BackUp.h"

#if defined(USEPWL)
#include <stdarg.h>
#include "PwlInterface.h"
#endif
#if defined(CCS_5728)
#include <ti/csl/soc/am572x/src/cslr_soc_mpu_baseaddress.h>
#include <uart.h>
#endif

static void DarkLog_PwlSend(void);
static ENUM_INFOCODE_TYPE DarkLog_InfocodeJudge(uint16_t code);
static ENUM_CM_RETURN DarkLog_TypeState(ENUM_LOG_TYPE type);
static void DarLog_WriteDisable(ENUM_LOG_TYPE type,const void *info, uint16_t code, uint16_t len);
static void DarkLog_PwlWriteEnable(ENUM_LOG_TYPE type,const void *info, uint16_t code, uint16_t len);

/** 首周期号开关*/
UINT8 KEY = 0;
static STRU_DARKLOG_TOTAL s_struDarkLogTotal;
static STRU_DARKLOG_WorkCycle s_struDarkLogWorkCycle;
/**暗文日志记录结果类型**/
UINT8 LOGRESURT_OK = 0x55;     /*暗文打印结果成功*/
UINT8 LOGRESURT_EER = 0xaa;    /*暗文打印结果失败*/

extern STRU_CM_QUEUE *p_BackUp_Dark_UsingLogQ ;

/**
* @brief     暗文日志初始化函数
* @details   根据传入的指针初始化暗文日志函数
* @param     LOGPRINTSENDFUNC pwlFunc   暗文日志驱动注册函数指针
* @return      无
* @author     刘继超
* @date      2022.8.20
* @note        无
*/
void DarkLog_Inital(LOGPRINTSENDFUNC pwlFunc)
{
    /** PowerLink发送暗文日志队列初始化*/
     (void)CM_StaticQueueInitial(&s_struDarkLogTotal.s_darkLogInfo.g_MSCP_PWL_DarkLogQ, DARKLOG_QUEUE_LEN,s_struDarkLogTotal.s_darkLogInfo.g_MSCP_PWL_DarkLogQBuf);
     s_struDarkLogTotal.s_darkLogInfo.counter = 0;
     s_struDarkLogTotal.s_darkLogInfo.packsize = DARKLOG_SENDPACK_INITAL_SIZE;
     s_struDarkLogTotal.s_darkLogInfo.sequenceNum = 0;

     /** 日志记录类型开关状态初始化*/
     s_struDarkLogTotal.s_darkLogType.err = DARKERR_LOG;
     s_struDarkLogTotal.s_darkLogType.debug = DARKDEBUG_LOG;
     s_struDarkLogTotal.s_darkLogType.prompt = DARKPROMPT_LOG;
     s_struDarkLogTotal.s_darkLogType.warning = DARKWARNING_LOG;
     /** 参数不为空*/
     if(NULL != pwlFunc)
     {
         /** 日志记录功能开或关*/
         if(LOGSWITCH_ON == DARKLOG_SWITCH)
         {
             /** 输出接口初始化*/
             s_struDarkLogTotal.s_darkLog_PwlFunc = pwlFunc;
             s_struDarkLogTotal.s_darkLog_PrintFunc = DarkLog_PwlWriteEnable;
             s_struDarkLogWorkCycle.SYN_FIRST = Plat_HardSync_GetCurrWorkCycle();
             s_struDarkLogWorkCycle.SYN = s_struDarkLogWorkCycle.SYN_FIRST;
             s_struDarkLogWorkCycle.Temp_SYN = s_struDarkLogWorkCycle.SYN_FIRST;
             s_struDarkLogWorkCycle.SYN_MIN = s_struDarkLogWorkCycle.SYN_FIRST;

         }
         else
         {
             /** 输出接口初始化*/
             s_struDarkLogTotal.s_darkLog_PwlFunc = PwlNullFunc;
             s_struDarkLogTotal.s_darkLog_PrintFunc = DarLog_WriteDisable;
         }
     }
     /** 参数为空*/
     else
     {
         ;/** 空*/
     }

}
#if 0
/*
* 功能描述:     暗文日志平台周期注册函数
* 输入参数:    DARKLOGPLMCYCFUNC plfmDarkLogcycfun   暗文日志平台周期注册函数指针
*               uint32_t code    平台周期信息编码
* 输入输出参数:
* 输出参数:     void
* 全局变量:
* 返回值:      ENUM_CM_RETURN
*/
ENUM_CM_RETURN PlfmDarkLogCycRegister(DARKLOGPLFMCYCFUNC plfmDarkLogcycfun,uint32_t code)
{
    ENUM_CM_RETURN ret = ENUM_CM_TRUE;
    s_struDarkLogTotal.s_darkLog_PlfmCycFunc = plfmDarkLogcycfun;
    s_struDarkLogTotal.darklog_PlfmCycCode = code;
    return ret;
}


/*
* 功能描述:     暗文日志应用周期注册函数
* 输入参数:    DARKLOGAPPCYCFUNC appDarkLogcycfun   暗文日志应用周期注册函数指针
*              uint32_t code    应用周期信息编码
* 输入输出参数:
* 输出参数:     void
* 全局变量:
* 返回值:      ENUM_CM_RETURN
*/

ENUM_CM_RETURN AppDarkLogCycRegister(DARKLOGAPPCYCFUNC appDarkLogcycfun,uint32_t code)
{
    ENUM_CM_RETURN ret = ENUM_CM_TRUE;
    s_struDarkLogTotal.s_darkLog_AppCycFunc = appDarkLogcycfun;
    s_struDarkLogTotal.darklog_AppCycCode = code;
    return ret;
}
#endif
/**
* @brief     暗文日志函数
* @details   无
* @param     ENUM_LOG_TYPE type ，输入，调试类型：ENUM_LOG_ERR错误类型、ENUM_LOG_WARNING警告类型、ENUM_LOG_PROMPT提示类型、ENUM_LOG_DEBUG调试类型
*            void *info ，输入，日志信息：非空指针
*            uint16_t code ，输入，日志信息编码：0-0xFFFF
*            uint8_t len ，输入，日志长度：0-0xFF
* @return    无
* @author    刘继超
* @date      2022.8.20
* @note      无
*/
static void DarkLog_PwlWriteEnable(ENUM_LOG_TYPE type,const void *info, uint16_t code, uint16_t len)
{
    /** 变量初始化*/
    ENUM_INFOCODE_TYPE codeType = ENUM_ERR_INFOCODE;
    UINT16 smallPackLength = 0;
    UINT8 packLength[2] = {0};
#if (1 == IS_5728_MCP)
    UINT8 smallPack[3000] = {0};
#elif ((1 ==IS_570_IPB)||(1 ==IS_570_OPB)||(1 ==IS_570_SIG))
    UINT8 smallPack[512]={0};
#endif
    UINT16 arrNumber = 0;
    UINT16 typeCode = 0;
    /** 参数防空且长度在合法范围内*/
    if(info != NULL && len >0u && len <= DARKLOG_SENDPACK_NORMAL_SIZE-18u)/** ljw 2025.2.19 数组类型有效长度判断为len+4B(2B暗文编码+2B数组长度) */
    {
        /** 首周期号开关打开*/
        if(KEY == 0u)
        {
            /** 更新周期号*/
            s_struDarkLogWorkCycle.Temp_SYN = s_struDarkLogWorkCycle.SYN;
            s_struDarkLogWorkCycle.SYN = Plat_HardSync_GetCurrWorkCycle();
            /** 周期号第一次变更*/
            if((s_struDarkLogWorkCycle.SYN != s_struDarkLogWorkCycle.Temp_SYN) && (s_struDarkLogWorkCycle.Temp_SYN == s_struDarkLogWorkCycle.SYN_FIRST))
            {
                /** 赋值周期号*/
                s_struDarkLogWorkCycle.SYN_MIN = s_struDarkLogWorkCycle.SYN;
                /** 关闭首周期号开关*/
                KEY = 1;
            }
            else
            {
                ;
            }
        }
        /** 首周期号开关关闭*/
        else
        {
            ;
        }
        /** 获取信息类型*/
        codeType = DarkLog_InfocodeJudge(code);
        switch(codeType)
        {
        case ENUM_ERR_INFOCODE:
            break;
        case ENUM_SINGLEBYTE_INFOCODE:
            /** 单字节信息写入*/
            typeCode = (UINT16)(((((UINT16)type - 1u) << 14) & 0xC000u) | (code & 0x3FFFu));
            CM_ShortToChar(typeCode,&smallPack[0]);
            smallPack[2] = *(const UINT8*)info;
            /** 数据长度*/
            smallPackLength = 3;
            CM_ShortToChar(smallPackLength,&packLength[0]);
            /** 先写入数据长度*/
            (void)CM_QueueWrite(2,packLength,&s_struDarkLogTotal.s_darkLogInfo.g_MSCP_PWL_DarkLogQ);
            /** 再写入数据内容*/
            (void)CM_QueueWrite(smallPackLength,smallPack,&s_struDarkLogTotal.s_darkLogInfo.g_MSCP_PWL_DarkLogQ);
            s_struDarkLogTotal.s_darkLogInfo.counter++;

            /** 写入日志备份队列*/
            (void)CM_QueueWrite(2,packLength,p_BackUp_Dark_UsingLogQ);
            (void)CM_QueueWrite(smallPackLength,smallPack,p_BackUp_Dark_UsingLogQ);
            break;
        case ENUM_DOUBLEBYTE_INFOCODE:
            /** 双字节信息写入*/
            typeCode = (UINT16)(((((UINT16)type - 1u) << 14) & 0xC000u) | (code & 0x3FFFu));
            CM_ShortToChar(typeCode,&smallPack[0]);

            CM_ShortToChar(*(const UINT16*)info,&smallPack[2]);
            /** 数据长度*/
            smallPackLength = 4;
            CM_ShortToChar(smallPackLength,&packLength[0]);
            /** 先写入数据长度*/
            (void)CM_QueueWrite(2,packLength,&s_struDarkLogTotal.s_darkLogInfo.g_MSCP_PWL_DarkLogQ);
            /** 再写入数据内容*/
            (void)CM_QueueWrite(smallPackLength,smallPack,&s_struDarkLogTotal.s_darkLogInfo.g_MSCP_PWL_DarkLogQ);
            s_struDarkLogTotal.s_darkLogInfo.counter++;
            /** 写入日志备份队列*/
            (void)CM_QueueWrite(2,packLength,p_BackUp_Dark_UsingLogQ);
            (void)CM_QueueWrite(smallPackLength,smallPack,p_BackUp_Dark_UsingLogQ);
            break;
        case ENUM_FOURBYTE_INFOCODE:
            /** 四字节信息写入*/
            typeCode = (UINT16)(((((UINT16)type - 1u) << 14) & 0xC000u) | (code & 0x3FFFu));
            CM_ShortToChar(typeCode,&smallPack[0]);

            CM_LongToChar(*(const UINT32*)info,&smallPack[2]);
            /** 数据长度*/
            smallPackLength = 6;
            CM_ShortToChar(smallPackLength,&packLength[0]);
            /** 先写入数据长度*/
            (void)CM_QueueWrite(2,packLength,&s_struDarkLogTotal.s_darkLogInfo.g_MSCP_PWL_DarkLogQ);
            /** 再写入数据内容*/
            (void)CM_QueueWrite(smallPackLength,smallPack,&s_struDarkLogTotal.s_darkLogInfo.g_MSCP_PWL_DarkLogQ);
            s_struDarkLogTotal.s_darkLogInfo.counter++;
            /** 写入日志备份队列*/
            (void)CM_QueueWrite(2,packLength,p_BackUp_Dark_UsingLogQ);
            (void)CM_QueueWrite(smallPackLength,smallPack,p_BackUp_Dark_UsingLogQ);
            break;
        case ENUM_ARRAY_INFOCODE:
            /** 数组信息写入*/
            typeCode = (UINT16)(((((UINT16)type - 1u) << 14) & 0xC000u) | (code & 0x3FFFu));
            CM_ShortToChar(typeCode,&smallPack[0]);
            //smallPack[2] = len;
            CM_ShortToChar(len,&smallPack[2]);
            /** 数据长度*/
            smallPackLength = len + 4u;   //小包数据长度为 信息编码（2）+ 数组数据长度(1) + 数据（len）
            CM_ShortToChar(smallPackLength,&packLength[0]);

            /** 更新数组下标*/
            for(arrNumber = 0; arrNumber < len; arrNumber++)
            {
                /** 写入数组*/
                smallPack[arrNumber + 4u] = ((const UINT8*)info)[arrNumber];
            }
            /** 先写入数据长度*/
            (void)CM_QueueWrite(2,packLength,&s_struDarkLogTotal.s_darkLogInfo.g_MSCP_PWL_DarkLogQ);//小包数据长度写入
            /** 再写入数据内容*/
           (void)CM_QueueWrite(smallPackLength,smallPack,&s_struDarkLogTotal.s_darkLogInfo.g_MSCP_PWL_DarkLogQ);
            s_struDarkLogTotal.s_darkLogInfo.counter++;

            /** 写入日志备份队列*/
            (void)CM_QueueWrite(2,packLength,p_BackUp_Dark_UsingLogQ);
            (void)CM_QueueWrite(smallPackLength,smallPack,p_BackUp_Dark_UsingLogQ);
            break;
        case ENUM_CLEAR_INFOCODE:
            /** 明文信息写入*/
            typeCode = (UINT16)(((((UINT16)type - 1u) << 14) & 0xC000u) | (code & 0x3FFFu));
            CM_ShortToChar(typeCode,&smallPack[0]);
            //smallPack[2] = len;
            CM_ShortToChar(len,&smallPack[2]);
            /** 数据长度*/
            smallPackLength = len + 4u;   //小包数据长度为 信息编码（2）+ 数组数据长度(1) + 数据（len）
            CM_ShortToChar(smallPackLength,&packLength[0]);

            /** 更新数组下标*/
            for(arrNumber = 0; arrNumber < len; arrNumber++)
            {
                /** 写入数组*/
                smallPack[arrNumber + 4u] = ((const UINT8*)info)[arrNumber];
            }
			/** 写入数据内容*/
            (void)CM_QueueWrite(2,packLength,&s_struDarkLogTotal.s_darkLogInfo.g_MSCP_PWL_DarkLogQ);//小包数据长度写入
            (void)CM_QueueWrite(smallPackLength,smallPack,&s_struDarkLogTotal.s_darkLogInfo.g_MSCP_PWL_DarkLogQ);
            s_struDarkLogTotal.s_darkLogInfo.counter++;

            /** 写入日志备份队列*/
            (void)CM_QueueWrite(2,packLength,p_BackUp_Dark_UsingLogQ);
            (void)CM_QueueWrite(smallPackLength,smallPack,p_BackUp_Dark_UsingLogQ);
            break;
        default:
            /*退出switch*/
            break;
        }
        /** 发送暗文日志*/
        DarkLog_PwlSend();
    }
    else
    {
        /** 输入格式有误*/
       if( len > DARKLOG_SENDPACK_NORMAL_SIZE-18u)
       {
           DarkLogPrint(ENUM_LOG_ERR,&code,LOGTYPE_ILLEGAID,2);
       }
    }

}

/**
* @brief     暗文日志写入错误函数
* @details   无
* @param     ENUM_LOG_TYPE type ，输入，调试类型：ENUM_LOG_ERR错误类型、ENUM_LOG_WARNING警告类型、ENUM_LOG_PROMPT提示类型、ENUM_LOG_DEBUG调试类型
*            void *info ，输入，日志信息：非空指针
*            uint16_t code ，输入，日志信息编码：0-0xFFFF
*            uint8_t len ，输入，日志长度：0-0xFF
* @return    无
* @author    刘继超
* @date      2022.8.20
* @note      无
*/
static void DarLog_WriteDisable(ENUM_LOG_TYPE type,const void *info, uint16_t code, uint16_t len)
{
    ;/** 写入失败*/
}

/**
* @brief     暗文日志接口函数
* @details   无
* @param     ENUM_LOG_TYPE type ，输入，调试类型：ENUM_LOG_ERR错误类型、ENUM_LOG_WARNING警告类型、ENUM_LOG_PROMPT提示类型、ENUM_LOG_DEBUG调试类型
*            void *info ，输入，日志信息：非空指针
*            uint16_t code ，输入，日志信息编码：0-0xFFFF
*            uint8_t len ，输入，日志长度：0-0xFF
* @return    无
* @author    刘继超
* @date      2022.8.20
* @note      无
*/
void DarkLogPrint(ENUM_LOG_TYPE type, const void *info, uint16_t code, uint16_t len)
{
    /** 变量初始化*/
    ENUM_CM_RETURN Rtntemp = ENUM_CM_FALSE;
    /** 读取日志类型状态*/
    Rtntemp = DarkLog_TypeState(type);
    /** 状态为真*/
    if(Rtntemp == ENUM_CM_TRUE && info != NULL && len > 0u)
    {
        /** 写入日志*/
        s_struDarkLogTotal.s_darkLog_PrintFunc(type,info,code,len);
    }
    else
    {
        /*明文  输入格式有错  最好串口打印也在*/
    }
}


/**
* @brief     暗文日志类型状态判断函数
* @details   无
* @param     ENUM_LOG_TYPE type ，输入，日志类型：错误类型LOG_ERR、警告类型LOG_WARNING、提示类型LOG_PROMPT、调试类型ENUM_LOG_DEBUG
*
* @return    ENUM_CM_RETURN 状态为开
*            ENUM_CM_FALSE  状态为关
* @author    刘继超
* @date      2022.8.20
* @note      无
*/
static ENUM_CM_RETURN DarkLog_TypeState(ENUM_LOG_TYPE type)
{
    ENUM_CM_RETURN Rtn = ENUM_CM_FALSE;
    /** 日志类型选择*/
    switch(type)
    {
    /** 错误类型日志*/
    case ENUM_LOG_ERR:
        Rtn = (LOGSWITCH_ON == s_struDarkLogTotal.s_darkLogType.err)?ENUM_CM_TRUE:ENUM_CM_FALSE;
        break;
    /** 警告类型日志*/
    case ENUM_LOG_WARNING:
        Rtn = (LOGSWITCH_ON == s_struDarkLogTotal.s_darkLogType.warning)?ENUM_CM_TRUE:ENUM_CM_FALSE;
        break;
    /** 提示类型日志*/
    case ENUM_LOG_PROMPT:
        Rtn = (LOGSWITCH_ON == s_struDarkLogTotal.s_darkLogType.prompt)?ENUM_CM_TRUE:ENUM_CM_FALSE;
        break;
    /** 调试类型日志*/
    case ENUM_LOG_DEBUG:
        Rtn = (LOGSWITCH_ON == s_struDarkLogTotal.s_darkLogType.debug)?ENUM_CM_TRUE:ENUM_CM_FALSE;
        break;
    default :
        Rtn = ENUM_CM_FALSE;
        break;
    }
    return Rtn;
}
/**
* @brief     日志信息范围判断函数
* @details   无
* @param     uint16_t code ，输入，信息范围，0-0xffff
* @return    ENUM_ERR_INFOCODE 编码错误
*            ENUM_SINGLEBYTE_INFOCODE  单字节
*            ENUM_DOUBLEBYTE_INFOCODE  双字节
*            ENUM_FOURBYTE_INFOCODE    四字节
*            ENUM_ARRAY_INFOCODE       数组
*            ENUM_CLEAR_INFOCODE       明文
* @author    刘继超
* @date      2022.8.20
* @note      无
*/
static ENUM_INFOCODE_TYPE DarkLog_InfocodeJudge(uint16_t code)
{
    ENUM_INFOCODE_TYPE ret = ENUM_ERR_INFOCODE;
    /** 信息范围在平台*/
    if(code <= PLFM_INFOCODEMAX )
    {
        /** 如果是明文信息*/
        if(code == CLEAR_INFOCODE)      /*明文*/
        {
            /** 返回结果：明文*/
            ret = ENUM_CLEAR_INFOCODE;
        }
        /** 如果是平台单字节信息*/
        else if(code > CLEAR_INFOCODE && code <= PLFM_SINGLEBYTE_INFOCODEMAX)/*平台单字节*/
        {
            /** 返回结果：单字节*/
            ret = ENUM_SINGLEBYTE_INFOCODE;
        }
        /** 如果是平台双字节信息*/
        else if(code > PLFM_SINGLEBYTE_INFOCODEMAX && code <= PLFM_DOUBLEBYTE_INFOCODEMAX)/*平台二字节*/
        {
            /** 返回结果：双字节*/
            ret = ENUM_DOUBLEBYTE_INFOCODE;
        }
        /** 如果是平台四字节信息*/
        else if(code > PLFM_DOUBLEBYTE_INFOCODEMAX && code <= PLFM_FOURBYTE_INFOCODEMAX)/*平台四字节*/
        {
            /** 返回结果：四字节*/
            ret = ENUM_FOURBYTE_INFOCODE;
        }
        /** 如果是平台数组信息*/
        else if(code > PLFM_FOURBYTE_INFOCODEMAX && code <= PLFM_ARRAY_INFOCODEMAX)/*平台数组*/
        {
            /** 返回结果：数组*/
            ret = ENUM_ARRAY_INFOCODE;
        }
        /** 其他情况*/
        else
        {
            /** 返回结果：错误*/
            ret = ENUM_ERR_INFOCODE;
        }
    }
    /** 信息范围在应用*/
    else if(code <= APP_INFOCODEMAX && code > PLFM_INFOCODEMAX)
    {
        /** 如果是单字节信息*/
        if(code <= APP_SINGLEBYTE_INFOCODE)/*应用单字节*/
        {
            /** 返回结果：明文*/
            ret = ENUM_SINGLEBYTE_INFOCODE;
        }
        /** 如果是双字节信息*/
        else if(code > APP_SINGLEBYTE_INFOCODE && code <= APP_DOUBLEBYTE_INFOCODE)/*应用二字节*/
        {
            /** 返回结果：双字节*/
            ret = ENUM_DOUBLEBYTE_INFOCODE;
        }
        /** 如果是四字节信息*/
        else if(code > APP_DOUBLEBYTE_INFOCODE && code <= APP_FOURBYTE_INFOCODE)/*应用四字节*/
        {
            /** 返回结果：四字节*/
            ret = ENUM_FOURBYTE_INFOCODE;
        }
        /** 如果是数组信息*/
        else if(code > APP_FOURBYTE_INFOCODE && code <= APP_ARRAY_INFOCODE)/*应用数组*/
        {
            /** 返回结果：数组*/
            ret = ENUM_ARRAY_INFOCODE;
        }
        /** 如果是其他信息*/
        else
        {
            /** 返回结果：错误*/
            ret = ENUM_ERR_INFOCODE;
        }
    }
    /** 信息范围超出*/
    else
    {
        /** 返回结果：错误*/
        ret = ENUM_ERR_INFOCODE;
    }

    return ret;
}


/**
* @brief     日志信息组PWL包函数
* @details   无
* @param     无
* @return    无
* @author    刘继超
* @date      2022.8.20
* @note      无
*/
static void DarkLog_PwlSend(void)
{
    /** 变量初始化*/
    UINT8 TempBuf[3];        /*获取记录长度的临时数组*/
    UINT8 SendBuf[1000]={0};     /*组包的发送数组*/
    UINT16 DateLenth = 0;    /*发送数组已存的数据长度*/
    UINT16 LogLenth = 0;     /*获取小包长度*/
    UINT16 BufSize = 0 ;     /*透传帧头字节长度*/
    UINT16 BoardID = 0 ;    /*板卡类型*/
    UINT32 QueDateLenth = 0; /*队列剩余数据长度*/
    UINT8  ubuf[2000] = {0};
    ENUM_CM_RETURN resualt = ENUM_CM_FALSE;

    /** 从队列中读出队列中的数据长度*/
    QueDateLenth = CM_QueueStatus(&s_struDarkLogTotal.s_darkLogInfo.g_MSCP_PWL_DarkLogQ);
    /** 队列中的有效数据满足组包条件     及  队列总长度 > 单包长度+ 记录数*1（队列中长度占用的字节）2*/
    while((QueDateLenth) > (s_struDarkLogTotal.s_darkLogInfo.packsize + (s_struDarkLogTotal.s_darkLogInfo.counter*2u)))
    {
        /** 4字节 记录帧类型*/
        CM_LongToChar(MSCP_CPUMsgType_DarkLogToRCD,&SendBuf[BufSize]);
        BufSize += 4u;
        /** 2字节 板卡类型*/
        BoardID = MSCP_CFM_GetLocalCPUId();
        CM_ShortToChar(BoardID,&SendBuf[BufSize]);
        BufSize += 2u;
        /** 2字节 数据长度：只包含数据长度*/
        BufSize += 2u;

        SendBuf[BufSize + DateLenth] = 0xFF;
        DateLenth += 1u;
        CM_LongToChar(s_struDarkLogTotal.s_darkLogInfo.sequenceNum,&SendBuf[BufSize + DateLenth]);
        DateLenth += 4u;
        /** 2字节 数据内容总长度*/
        DateLenth += 2u;
        /** 周期号信息编码*/
        CM_ShortToChar(LOGTYPE_FIRSTCYC,&SendBuf[BufSize + DateLenth]);
        DateLenth += 2u;
        /** 单包的首周期号*/
        CM_LongToChar(s_struDarkLogWorkCycle.SYN_MIN,&SendBuf[BufSize + DateLenth]);
        DateLenth += 4u;
        /** 循环送队列中取长度、取数据组包*/
        while(1)
        {
            /** 读取记录长度*/
            resualt = CM_QueueScan(2, &TempBuf[0],&s_struDarkLogTotal.s_darkLogInfo.g_MSCP_PWL_DarkLogQ);
            LogLenth = CM_ShortFromChar(&TempBuf[0]);
            /** 扫描队列长度成功*/
            if(resualt == ENUM_CM_TRUE)
            {
                /** 判断该包剩余空间是否能存下该记录，可以存下即组包*/
                if((DateLenth+LogLenth + 1u) <= s_struDarkLogTotal.s_darkLogInfo.packsize)  //这里加一是给帧尾留位置
                {
                   /** 将长度读出，丢弃*/
                   (void)CM_QueueRead(2, &TempBuf[0],&s_struDarkLogTotal.s_darkLogInfo.g_MSCP_PWL_DarkLogQ);
                   /** 读出记录存到发送数组中*/
                   (void)CM_QueueRead(LogLenth, &SendBuf[BufSize+DateLenth],&s_struDarkLogTotal.s_darkLogInfo.g_MSCP_PWL_DarkLogQ);
                   s_struDarkLogTotal.s_darkLogInfo.counter--;
                   /** 更新已存数据长度*/
                   DateLenth += LogLenth;
                }
                /** 单包长度过长*/
                else if(LogLenth > s_struDarkLogTotal.s_darkLogInfo.packsize-14u)
                {
                    /** 将长度读出，丢弃*/
                    (void)CM_QueueRead(2, &ubuf[0],&s_struDarkLogTotal.s_darkLogInfo.g_MSCP_PWL_DarkLogQ);
                    /** 读出记录存到发送数组中*/
                    (void)CM_QueueRead(LogLenth, &ubuf[1],&s_struDarkLogTotal.s_darkLogInfo.g_MSCP_PWL_DarkLogQ);

                    s_struDarkLogTotal.s_darkLogInfo.counter--;
                }
                /** 队列中数据不足一包*/
                else
                {
                    /** 组包尾*/
                    SendBuf[BufSize+DateLenth] = 0xFE;
                    DateLenth++;

                    CM_ShortToChar((DateLenth),&SendBuf[6]);//发送记录板总长度，
                    /*总长度*/

                    CM_ShortToChar((DateLenth),&SendBuf[13]);//发送上位机长度。
                    /*发送组好的包到记录板*/
                    /** 如果日志量过大*/
                    if(DARKLOG_SENDPACK_INITAL_SIZE == s_struDarkLogTotal.s_darkLogInfo.packsize)
                    {
                        /** 上电日志数量过多，无法发送日志*/
                        #if 1 == IS_5728_MCP
                        UARTPrintf("PowerOn Log is Over!!\r\n");  /*通过串口打印*/
                        #elif ((1 ==IS_570_IPB)||(1 ==IS_570_OPB)||(1 ==IS_570_SIG))
                        Tms570printf("PowerOn Log is Over!!\r\n");  /*通过串口打印*/
                        #endif

                    }
                    else
                    {
                        /** 给一端记录板发送日志*/
                        (void)s_struDarkLogTotal.s_darkLog_PwlFunc(PWL_SEND_LOWLEVEL,MSCP_BOARD_LR_TC1_A1,&SendBuf[0],BufSize+DateLenth);
                        s_struDarkLogTotal.s_darkLogInfo.sequenceNum++;
                    }
                    /** 清空发送数组*/
                    CM_Memset(&SendBuf[0], 0, 1000);
                    CM_Memset(&TempBuf[0],0,3);



                    /** 数组长度和日志数据长度清0*/
                    BufSize = 0;
                    DateLenth = 0;

                    /** 完成一次组包，跳出当前组包循环*/
                    break;
                }
            }
            else
            {
                /** 队列扫描长度失败，则直接跳出循环防止死在循环里*/
                break;
            }
        }
        KEY = 0;
        /** 重新获取队列长度*/
        QueDateLenth = CM_QueueStatus(&s_struDarkLogTotal.s_darkLogInfo.g_MSCP_PWL_DarkLogQ);

    }
    if(KEY == 0u)
    {
        /** 恢复初始周期号*/
        s_struDarkLogWorkCycle.SYN = s_struDarkLogWorkCycle.SYN_FIRST;
        s_struDarkLogWorkCycle.SYN_MIN = s_struDarkLogWorkCycle.SYN_FIRST;
        s_struDarkLogWorkCycle.Temp_SYN = s_struDarkLogWorkCycle.SYN_FIRST;
    }

}


/**
* @brief     重新设置暗文组宝大小
* @details   无
* @param     UINT16 packsize，输入，组包大小
* @return    无
* @author    刘继超
* @date      2022.8.20
* @note      无
*/
void Set_DarkLogPackSize(UINT16 packsize)
{

    /** 重新设置暗文组宝大小*/
    s_struDarkLogTotal.s_darkLogInfo.packsize = packsize;
    DarkLog_PwlSend();
}

/**
* @brief     异常状态日志处理函数
* @details   无
* @param     无
* @return    无
* @author    刘继超
* @date      2022.8.20
* @note      无
*/
void DarkLog_FaultStateLogPrint(void)
{
    /** 变量初始化*/
    UINT8 TempBuf[3];        /*获取记录长度的临时数组*/
    UINT8 SendBuf[1000]={0};     /*组包的发送数组*/
    UINT16 DateLenth = 0;    /*发送数组已存的数据长度*/
    UINT16 LogLenth = 0;     /*获取小包长度*/
    UINT16 BufSize = 0 ;     /*透传帧头字节长度*/
    UINT16 BoardID = 0 ;    /*板卡类型*/
    UINT32 QueDateLenth = 0; /*队列剩余数据长度*/
        /** 从队列中读出队列中的数据长度*/
        QueDateLenth = CM_QueueStatus(&s_struDarkLogTotal.s_darkLogInfo.g_MSCP_PWL_DarkLogQ);
        /** 队列中的有效数据满足组包条件     及  队列总长度 > 单包长度+ 记录数*1（队列中长度占用的字节）2*/
        while((QueDateLenth) > 0u)
        {
            /** 4字节 记录帧类型*/
            CM_LongToChar(MSCP_CPUMsgType_DarkLogToRCD,&SendBuf[BufSize]);
            BufSize += 4u;
            /** 2字节 板卡类型*/
            BoardID = MSCP_CFM_GetLocalCPUId();
            CM_ShortToChar(BoardID,&SendBuf[BufSize]);
            BufSize += 2u;
            /** 2字节 数据长度：只包含数据长度*/
            BufSize += 2u;

            SendBuf[BufSize + DateLenth] = 0xFF;
            DateLenth += 1u;
            CM_LongToChar(s_struDarkLogTotal.s_darkLogInfo.sequenceNum,&SendBuf[BufSize + DateLenth]);
            DateLenth += 4u;
            /** 2字节 数据内容总长度*/
            DateLenth += 2u;
            /** 周期号信息编码*/
            CM_ShortToChar(LOGTYPE_FIRSTCYC,&SendBuf[BufSize + DateLenth]);
            DateLenth += 2u;
            /** 单包的首周期号*/
            CM_LongToChar(s_struDarkLogWorkCycle.SYN_MIN,&SendBuf[BufSize + DateLenth]);
            DateLenth += 4u;
            /** 循环送队列中取长度、取数据组包*/
            while(1)
            {
                /** 读取记录长度*/
                (void)CM_QueueScan(2, &TempBuf[0],&s_struDarkLogTotal.s_darkLogInfo.g_MSCP_PWL_DarkLogQ);
                LogLenth = CM_ShortFromChar(&TempBuf[0]);

                QueDateLenth = CM_QueueStatus(&s_struDarkLogTotal.s_darkLogInfo.g_MSCP_PWL_DarkLogQ);

                /** 判断该包剩余空间是否能存下该记录，可以存下即组包*/
                if((DateLenth + LogLenth + 1u<= DARKLOG_SENDPACK_NORMAL_SIZE)&&( QueDateLenth > 0u))  //这里加一是给帧尾留位置--mjq_modify
                {
                   /** 将长度读出，丢弃*/
                   (void)CM_QueueRead(2, &TempBuf[0],&s_struDarkLogTotal.s_darkLogInfo.g_MSCP_PWL_DarkLogQ);
                   /** 读出记录存到发送数组中*/
                   (void)CM_QueueRead(LogLenth, &SendBuf[BufSize+DateLenth],&s_struDarkLogTotal.s_darkLogInfo.g_MSCP_PWL_DarkLogQ);
                   s_struDarkLogTotal.s_darkLogInfo.counter--;
                   /** 更新已存数据长度*/
                   DateLenth += LogLenth;
                }
                /** 队列中数据不足一包*/
                else
                {
                    SendBuf[BufSize+DateLenth] = 0xFE;
                    DateLenth++;
                    CM_ShortToChar((DateLenth),&SendBuf[6]);//发送记录板总长度，
                    /** 总长度*/
                    CM_ShortToChar((DateLenth),&SendBuf[13]);//发送上位机长度。
                    /*发送组好的包到记录板*/
                    /** 给一端记录板发送日志*/
                    (void)s_struDarkLogTotal.s_darkLog_PwlFunc(PWL_SEND_LOWLEVEL,MSCP_BOARD_LR_TC1_A1,&SendBuf[0],BufSize+DateLenth);
                    /** 给二端记录板发送日志*/

                    s_struDarkLogTotal.s_darkLogInfo.sequenceNum++;

                    /** 清空发送数组*/
                    CM_Memset(&SendBuf[0], 0, 1000);
                    CM_Memset(&TempBuf[0],0,3);

                    /** 恢复初始周期号*/
                    s_struDarkLogWorkCycle.SYN = s_struDarkLogWorkCycle.SYN_FIRST;
                    s_struDarkLogWorkCycle.SYN_MIN = s_struDarkLogWorkCycle.SYN_FIRST;
                    s_struDarkLogWorkCycle.Temp_SYN = s_struDarkLogWorkCycle.SYN_FIRST;


                    /** 数组长度和日志数据长度清0*/
                    BufSize = 0;
                    DateLenth = 0;

                    /** 完成一次组包，跳出当前组包循环*/
                    break;
                }
            }
            KEY = 0;
            /** 重新获取队列长度*/
            QueDateLenth = CM_QueueStatus(&s_struDarkLogTotal.s_darkLogInfo.g_MSCP_PWL_DarkLogQ);

        }
}


void ASSERTDarkLog(UINT8* file, UINT8* fun, UINT16 line)
{
    UINT8* value[2] = {file,fun};
    UINT8 arr[90] = {0};

    if((NULL != file) && (NULL != fun))
    {
        (void)CM_Memcpy(arr, 90, value[0], strlen(value[0]));
        (void)CM_Memcpy(&arr[40], 50u, value[1], strlen(value[1]));
        CM_ShortToChar(line, arr+80);

        DarkLogPrint(ENUM_LOG_PROMPT,arr,CLEAR_INFOCODE,90);
    }
    else
    {
        ;
    }
}




