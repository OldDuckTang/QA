import os
import time
import tensorflow as tf
import qaData
from qaLSTM import QaLstm


def restore():
    try:
        saver.restore(sess, trainedModel)
    except Exception as e:
        print("加载模型失败，重新开始训练")
        train()


def train():
    # 准备训练数据
    qTrain, aTrain, lTrain, qIdTrain = qaData.loadData(trainingFile, word2idx, unrollSteps, True)
    qDevelop, aDevelop, lDevelop, qIdDevelop = qaData.loadData(developFile, word2idx, unrollSteps, True)
    trainQuestionCounts = qIdTrain[-1] + 1
    for i in range(len(qIdDevelop)):
        qIdDevelop[i] += trainQuestionCounts
    tqs, tta, tfa = [], [], []
    for question, trueAnswer, falseAnswer in qaData.trainingBatchIter(qTrain + qDevelop, aTrain + aDevelop,
                                                                      lTrain + lDevelop, qIdTrain + qIdDevelop, batchSize):
        tqs.append(question), tta.append(trueAnswer), tfa.append(falseAnswer)
    # 开始训练
    sess.run(tf.global_variables_initializer())
    for i in range(lrDownCount):
        optimizer = tf.train.GradientDescentOptimizer(learningRate)
        optimizer.apply_gradients(zip(grads, tvars))
        trainOp = optimizer.apply_gradients(zip(grads, tvars), global_step=globalStep)
        for epoch in range(epochs):
            for question, trueAnswer, falseAnswer in zip(tqs, tta, tfa):
                startTime = time.time()
                feed_dict = {
                    lstm.ori_input_quests: question,
                    lstm.cand_input_quests: trueAnswer,
                    lstm.neg_input_quests: falseAnswer,
                    lstm.keep_prob: dropout
                }
                _, step, _, _, loss, acc = \
                    sess.run([trainOp, globalStep, lstm.ori_cand, lstm.ori_neg, lstm.loss, lstm.acc], feed_dict)
                timeUsed = time.time() - startTime
                print("step:", step, "loss:", loss, "acc:", acc, "time:", timeUsed)
            saver.save(sess, saveFile)
        learningRate *= lrDownRate


if __name__ == '__main__':
    # 定义参数
    trainingFile = "data/training.data"
    developFile = "data/develop.data"
    testingFile = "data/testing.data"
    resultFile = "predictRst.score"
    saveFile = "newModel/savedModel"
    trainedModel = "trainedModel/savedModel"
    embeddingFile = "word2vec/zhwiki_2017_03.sg_50d.word2vec"
    embeddingSize = 50  # 词向量的维度

    dropout = 1.0
    learningRate = 0.4  # 学习速度
    lrDownRate = 0.5  # 学习速度下降速度
    lrDownCount = 4  # 学习速度下降次数
    epochs = 20  # 每次学习速度指数下降之前执行的完整epoch次数
    batchSize = 20  # 每一批次处理的<b>问题</b>个数

    rnnSize = 100  # LSTM cell中隐藏层神经元的个数

    unrollSteps = 100  # 句子中的最大词汇数目
    max_grad_norm = 5

    allow_soft_placement = True  # Allow device soft device placement
    gpuMemUsage = 0.8  # 显存最大使用
    gpuDevice = "/gpu:0"  # GPU设备名

    # 读取测试数据
    embedding, word2idx = qaData.loadEmbedding(embeddingFile, embeddingSize)
    qTest, aTest, _, qIdTest = qaData.loadData(testingFile, word2idx, unrollSteps)

    # 配置TensorFlow
    with tf.Graph().as_default(), tf.device(gpuDevice):
        gpu_options = tf.GPUOptions(per_process_gpu_memory_fraction=gpuMemUsage)
        session_conf = tf.ConfigProto(allow_soft_placement=allow_soft_placement, gpu_options=gpu_options)
        with tf.Session(config=session_conf).as_default() as sess:
            # 加载LSTM网络
            globalStep = tf.Variable(0, name="globalStep", trainable=False)
            lstm = QaLstm(batchSize, unrollSteps, embedding, embeddingSize, rnnSize)
            tvars = tf.trainable_variables()
            grads, _ = tf.clip_by_global_norm(tf.gradients(lstm.loss, tvars), max_grad_norm)
            saver = tf.train.Saver()

            # 加载模型或训练模型
            if os.path.exists(trainedModel + '.index'):
                while True:
                    choice = input("找到已经训练好的模型，是否载入（y/n）")
                    if choice.strip().lower() == 'y':
                        restore()
                        break
                    elif choice.strip().lower() == 'n':
                        choice = input("您真的确定吗？重新训练会消耗大量时间与硬件资源（yes/no）")
                        if choice.strip().lower() == 'yes':
                            train()
                            break
                        elif choice.strip().lower() == 'no':
                            restore()
                            break
                        else:
                            print("无效的输入！\n")
                    else:
                        print("无效的输入！\n")
            else:
                train()
            # 进行测试，输出结果
            with open(resultFile, 'w') as file:
                for question, answer in qaData.testingBatchIter(qTest, aTest, batchSize):
                    feed_dict = {
                        lstm.test_input_q: question,
                        lstm.test_input_a: answer,
                        lstm.keep_prob: dropout
                    }
                    _, scores = sess.run([globalStep, lstm.test_q_a], feed_dict)
                    for score in scores:
                        file.write("%.9f" % score + '\n')
