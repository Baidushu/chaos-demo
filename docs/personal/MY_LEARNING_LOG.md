# 我的学习日志

> 文档定位：**个人练习与复盘记录**（可以空白、可以犯错、可以反复改）。  
> 不作为技术事实源；对外/对 AI 的**权威说明**见 [`../AI_PROJECT_CONTEXT.md`](../AI_PROJECT_CONTEXT.md) 与 [`../README.md`](../README.md)（文档地图）。  
> 需要叙述模板时可参考 `../interview/INTERVIEW_PREP.md` / `../intro/DEEP_DIVE.md`。

## Day 1: 理解项目启动流程

### 实验1：启动服务
**命令**：`docker compose up -d`

**我的理解**：
- [ ] 这条命令做了什么？（启动了哪些容器？）
- [ ] 为什么要用 `-d` 参数？
- [ ] 如何验证服务启动成功？

**实际操作记录**：
```
# 我执行的命令：


# 看到的输出：


# 遇到的问题：


# 解决方法：

```

---

### 实验2：发送第一个请求
**命令**：
```bash
curl -X POST http://localhost:5000/order \
  -H "Content-Type: application/json" \
  -d '{"item_id": "sku-1", "quantity": 2}'
```

**我的理解**：
- [ ] 这个请求到了哪个服务？
- [ ] 返回的 JSON 里有什么字段？
- [ ] order_id 是怎么生成的？

**实际操作记录**：
```
# 返回结果：


# 我的疑问：

```

---

### 实验3：测试幂等性
**命令**：
```bash
# 第一次请求（带幂等key）
curl -X POST http://localhost:5000/order \
  -H "Content-Type: application/json" \
  -H "X-Idempotency-Key: test-key-001" \
  -d '{"item_id": "sku-1", "quantity": 2}'

# 第二次请求（同样的key）
curl -X POST http://localhost:5000/order \
  -H "Content-Type: application/json" \
  -H "X-Idempotency-Key: test-key-001" \
  -d '{"item_id": "sku-1", "quantity": 2}'
```

**我的理解**：
- [ ] 两次请求返回的 order_id 一样吗？
- [ ] Redis 里存了什么？（用 `docker exec -it <redis容器> redis-cli` 查看）
- [ ] 如果不传 X-Idempotency-Key 会怎样？

**实际操作记录**：
```
# 第一次返回：


# 第二次返回：


# Redis 里的数据：


```

---

## Day 2: 理解代码核心逻辑

### 任务1：读懂 app.py 的订单创建流程
**目标**：能用自己的话解释 `/order` 接口做了什么

**阅读清单**：
- [ ] `app.py` 第 X 行到第 Y 行（创建订单的函数）
- [ ] 幂等检查在哪里？
- [ ] 限流检查在哪里？
- [ ] 超时保护在哪里？

**我的笔记**：
```python
# 伪代码：用自己的话写出流程
def create_order():
    # 1. 检查幂等key

    # 2. 检查限流

    # 3. 处理业务逻辑

    # 4. 返回结果
```

---

### 任务2：理解限流原理
**问题**：
- 限流是按什么维度的？（IP？用户？）
- 每秒最多多少请求？
- 超过限制返回什么状态码？

**实验**：
```bash
# 快速发送10个请求，看是否被限流
for i in {1..10}; do
  curl -X POST http://localhost:5000/order \
    -H "Content-Type: application/json" \
    -d '{"item_id": "sku-1", "quantity": 1}'
done
```

**我的发现**：


---

## Day 3: 理解压测与对比

（待补充...）

