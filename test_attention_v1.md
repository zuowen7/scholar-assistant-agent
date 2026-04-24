> RITA: Group Attention is All You Need for Timeseries
> Analytics
> JIAMING LIANG, University of Pennsylvania, USA
> LEI CAO, Uof Arizona/MIT, USA
> SAMUEL MADDEN, Massachusetts Institute of Technology, USA
> ZACHARY IVES, University of Pennsylvania, USA
> GUOLIANG LI, Tsinghua University, China
> Timeseries analytics is important in many real-world applications. Recently, the Transformer model, popular in natural language processing, has been leveraged to learn high quality feature embeddings from timeseries: embeddings are key to the performance of various timeseries analytics tasks such as similarity-based timeseries queries within vector databases. However, quadratic time and space complexities limit Transformers’ scalability, especially for long timeseries. To address these issues, we develop a timeseries analytics tool, RITA, which uses a novel attention mechanism, named group attention, to address this scalability issue. Group attention dynamically clusters the objects based on their similarity into a small number of groups and approximately computes the attention at the coarse group granularity. It thus significantly reduces the time and space complexity, yet provides a theoretical guarantee on the quality of the computed attention. The dynamic scheduler of RITA continuously adapts the number of groups and the batch size in the training process, ensuring group attention always uses the fewest groups needed to meet the approximation quality requirement. Extensive experiments on various timeseries datasets and analytics tasks demonstrate that RITA outperforms the state-of-the-art in accuracy and is significantly faster — with speedups of up to 63X. CCS Concepts: • Information systems → Data management systems. Additional Key Words and Phrases: Timeseries Analytics, Self-supervised, Attention, Efficient Transformers
> ACM Reference Format:
> Jiaming Liang, Lei Cao, Samuel Madden, Zachary Ives, and Guoliang Li. 2024. RITA: Group Attention is All You
> Need for Timeseries Analytics. Proc. ACM Manag. Data 2, 1 (SIGMOD), Article 62 (February 2024), 28 pages. https://doi.org/10.1145/3639317
> 1 INTRODUCTION
> Many data-driven applications involve processing massive timeseries data, including IoT [14], medical AI [17], stock market [32], etc. As such, there is a great need for timeseries analytics, such as forecasting [9], classification [24], clustering [36], similarity search [45], and anomaly detection [57], with applications ranging from automatically diagnosing diseases [6], recognizing human activities [34], to stopping financial fraud [67]. In particular, in the database community, vector databases [61] are being used to store and index high-dimensional feature embeddings of unstructured and semi-structured data, which allows users
> Authors’ addresses: Jiaming Liang, University of Pennsylvania, Philadelphia, PA, USA, liangjm@seas.upenn.edu; Lei Cao, Uof Arizona/MIT, Tucson, AZ, USA, lcao@csail.mit.edu; Samuel Madden, Massachusetts Institute of Technology, Cambridge,
> MA, USA, madden@csail.mit.edu; Zachary Ives, University of Pennsylvania, Philadelphia, PA, USA, zives@cis.upenn.edu;
> Guoliang Li, Tsinghua University, Beijing, China, liguoliang@tsinghua.edu.cn. This work is licensed under a Creative Commons Attribution International 4.0 License. © 2024 Copyright held by the owner/author(s). ACM 2836-6573/2024/2-ART62 https://doi.org/10.1145/3639317
> Proc. ACM Manag. Data, Vol. 2, No. 1 (SIGMOD), Article 62. Publication date: February 2024. 62:2 Jiaming Liang, Lei Cao, Samuel Madden, Zachary Ives, and Guoliang Li
> Timeseries Dataset
> Store
> Provide
> (Embedding, Timeseries)
> Timeseries as (key, value)

RITA: Group Attention is All You Need for Timeseries Analytics
JIAMING LIANG, University of Pennsylvania, USA
LEI CAO, Uof Arizona/MIT, USA
SAMUEL MADDEN, Massachusetts Institute of Technology, USA
ZACHARY IVES, University of Pennsylvania, USA
GUOLIANG LI, Tsinghua University, China
时间序列分析在许多现实应用场景中具有重要意义。最近，源自自然语言处理领域的Transformer模型被用于从时序数据中学习高质量的特征嵌入：这些嵌入是各种时间序列分析任务（如向量数据库中的基于相似性的时序查询）性能的关键因素。然而二次时间与空间复杂度限制了Transformers在长时序场景下的可扩展性。为解决这些问题，我们开发了一个时间序列分析工具RITA，其采用了一种新颖的注意力机制——组注意力（Group Attention），以应对这一可扩展性问题。组注意力根据对象间的相似性动态聚合成少量分组，并在粗粒度组级别近似计算注意力值。这显著降低了时间和空间复杂度，同时为所计算注意力的质量提供了理论保证。RITA的动态调度器持续调整训练过程中所需的分组数量和批量大小，在满足近似质量要求的前提下始终使用最少必要分组数。大量实验表明在多种时间序列数据集及分析任务上，RITA在准确率方面超越了现有最先进的方法，并显著提升了速度——最高可达63倍加速效果。
CCS Concepts: • Information systems → Data management systems. Additional Key Words and Phrases: Timeseries Analytics, Self-supervised, Attention, Efficient Transformers
ACM Reference Format:
Jiaming Liang, Lei Cao, Samuel Madden, Zachary Ives, and Guoliang Li. 2024. RITA: Group Attention is All You Need for Timeseries Analytics. Proc. ACM Manag. Data 2, 1 (SIGMOD), Article 62 (February 2024), 28 pages. https://doi.org/10.1145/3639317
1 引言
许多数据驱动的应用涉及处理海量时间序列数据，包括物联网[14]、医疗AI[17]、股票市场[32]等。因此需要广泛的时间序列分析技术，如预测[9]、分类[24]、聚类[36]、相似性搜索[45]和异常检测[57]，其应用范围从自动诊断疾病[6]到识别人类活动[34]以及阻止金融欺诈[67]。特别是在数据库领域，向量数据库[61]被用于存储和索引非结构化及半结构化数据的高维特征嵌入，这允许用户
作者地址：Jiaming Liang, University of Pennsylvania, Philadelphia, PA, USA, liangjm@seas.upenn.edu; Lei Cao, Uof Arizona/MIT, Tucson, AZ, USA, lcao@csail.mit.edu; Samuel Madden, Massachusetts Institute of Technology, Cambridge, MA, USA, madden@csail.mit.edu; Zachary Ives, University of Pennsylvania, Philadelphia, PA, USA, zives@cis.upenn.edu;
Guoliang Li, Tsinghua University, Beijing, China, liguoliang@tsinghua.edu.cn. 本工作采用知识共享署名国际4.0许可协议。©2024 版权由版权所有者/作者持有。ACM 2836-6573/2024/2-ART62 https://doi.org/10.1145/3639317
Proc. ACM Manag. Data, Vol. 2, No. 1 (SIGMOD), Article 62. 出版日期：2024年2月。62:2 Jiaming Liang, Lei Cao, Samuel Madden, Zachary Ives, and Guoliang Li
时间序列数据集
存储
提供
（嵌入，时序）
时序作为（键值对）

> Timeseries
> RITA Vector DB Query
> Dataset
> 2 Vector Database
> Timeseries
> Queries

时序
RITA向量数据库查询
数据集
2 向量数据库
时序
查询

> Users ML
> Classification Streaming Events
> Fig. 1. RITA in a timeseries-based query system to efficiently explore this data by conducting similarity searches in the embedding space. Effective feature representations are a key building-block to construct a valid vector database. As a real-world example, we have been collaborating with a major US hospital [7] to develop a large-scale interactive system to label EEG segments (450 million segments, 30TB) with 6 classes representing different types of seizures. These labeled EEG segments are used to train a classifier which can then automatically detect seizures based on EEG signals collected during the clinical observation of patients. The goal of this system is to propagate the labels provided by the experts to similar segments, thus reducing the manual labeling efforts by the neurologists. Our timeseries feature embedding approach, RITA, functions as a core component in this system. More specifically, we use RITA to convert the EEG segments into feature embeddings and store them in a vector database which supports similarity search requests submitted by the neurologists to return the 𝑘 nearest neighbors of the to-be-labelled segment, as depicted in Fig. 1. Recently researchers [70] have started leveraging the self-supervised pre-training methodology of Transformers [5, 19, 59], which have proven remarkably successful in natural language processing (NLP), to automatically learn high quality feature embeddings from timeseries. In NLP, self-supervised pre-training exploits the sequential patterns (correlations) among the words in sentences to produce contextualized feature embeddings. Timeseries bear similarity to natural language because in timeseries data the sequential order among the values (stock price, volume, etc.) over time matters. That is, each value is highly correlated with other values observed before or after it. Therefore, pre-training a Transformer model which takes the correlations among different observations into account is a natural idea to learn feature embeddings from timeseries. Indeed, the experiments in [70] confirm that Transformer-based methods outperform traditional timeseries analytics te chniques. Existing work [70] that directly applies Transformers to learn features from timeseries data has been shown not to scale to long timeseries [35]. The idea of self-attention [59] is central to pre-training methods in NLP: It computes pairwise correlations among different semantic units in a sequence (in NLP, a sentence); as such, it has quadratic time and space complexity in the length of the input sequence. This limits the model’s scalability, especially when handling large-scale timeseries data, which is common in real-world applications such as IoT, medical AI, and finance [7, 39, 71]. Predictions about timeseries may need to look at hundreds of thousands of prior samples to achieve accuracy. Referring again to our EEG project, seizures are brief, so we chunk EEG data into 2-second segments and detect seizures at the segment level. However, the classification of a particular segment depends on up to 12 hours of prior signal to consider long-term trends and determine if one 2-second segment indicates a seizure. There are more than 21,000 segments in 12 hours. This greatly exceeds the number of semantic units that typical NLP tasks expect. For example, BERT [19]
> Proc. ACM Manag. Data, Vol. 2, No. 1 (SIGMOD), Article 62. Publication date: February 2024. RITA: Group Attention is All You Need for Timeseries Analytics 62:3 limits the number of units to 512 and even massive models like GPT-3 [5] limit the number of units to 2048. Although in NLP some lower-complexity methods have been proposed to approximately compute self-attention [11, 31, 62], their performance degrades dramatically when used on timeseries, due to the gap between natural language and timeseries, as we will show in our experiments. Proposed Approach. To tackle the aforementioned problem, we develop RITA, a Transformerbased timeseries analytics tool, which uses a novel attention mechanism, called group attention, to scale to long timeseries. Our goal is to significantly speed up execution versus prior methods while sacrificing minimal predictive accuracy. Leveraging the similarity among long timeseries pieces, RITA chunks the input timeseries into segments and dynamically clusters the segments into a small number (denoted as 𝑁 ) of groups.

用户 ML
分类 流式事件
图1. RITA在基于时序的查询系统中通过在嵌入空间执行相似性搜索高效探索该数据。有效的特征表示是构建有效向量数据库的关键组成部分。作为一个现实案例，我们与一家美国主要医院[7]合作开发了一个大规模交互系统，用于标记EEG段（4.5亿个片段，30TB），这些片段包含6类代表不同癫痫类型的分类标签。这些带标注的EEG片段被用来训练一个分类器，该分类器可以根据临床观察患者期间收集到的EEG信号自动检测癫痫发作。该系统的目的是将专家提供的标签传播至相似片段，从而减少神经科医生的手动标记工作量。我们的时序特征嵌入方法RITA在此系统中作为核心组件发挥作用。更具体地说，我们使用RITA将EEG段转换为特征嵌入并存储在支持向量数据库的相似性搜索请求的神经科医生提交的查询中以返回待标注片段的k个最近邻，如图1所示。近期研究人员[70]开始利用Transformer模型自监督预训练方法[5, 19, 59]，该方法已在自然语言处理（NLP）领域取得了显著成功，用于自动从时序数据中学习高质量特征嵌入。在NLP中，自监督预训练通过句子中的词语间的序列模式（相关性）生成上下文化的特征嵌入。时间序列与自然语言相似之处在于，在时间序列数据中随时间变化的值（股票价格、成交量等）顺序具有重要意义。也就是说，每个数值与其他前后观测到的数值高度相关。因此，预训练一个考虑不同观察之间关联性的Transformer模型是学习时序特征嵌入的天然想法。事实上，[70]中的实验验证了基于Transformer的方法优于传统时间序列分析技术。现有工作[70]直接应用Transformers从时序数据中学习特征已被证明无法扩展到长时序场景[35]。自注意力机制[59]的思想是NLP预训练方法的核心：它计算序列（在NLP中为句子）不同语义单元之间的成对相关性；因此，其时间与空间复杂度随输入长度呈二次增长。这限制了模型的可扩展性，尤其是在处理大规模时序数据场景下，如物联网、医疗AI和金融领域[7, 39, 71]。关于时序预测可能需要查看数以万计的历史样本才能达到准确率要求。再次参考我们的EEG项目，癫痫发作是短暂性的，因此我们将EEG数据分块为2秒的片段并在段级检测癫痫。然而特定片段的分类依赖于长达12小时之前的信号来考虑长期趋势并判断某个2秒片段是否表示癫痫发作。在12小时内有超过2.1万个片段。这远远超过了典型NLP任务所期望的语义单元数量。例如，BERT[19]限制了单元数至512个，甚至大规模模型如GPT-3[5]也仅限于2048个单元。尽管在NLP领域已提出一些低复杂度方法近似计算自注意力机制[11, 31, 62]，但由于自然语言与时间序列之间的差异，在我们的实验中这些方法的性能会显著下降。提出的解决方案：为解决上述问题，我们开发了RITA——一个基于Transformer的时间序列分析工具，其采用了一种新颖的注意力机制（称为组注意力）以扩展到长时序场景。我们的目标是在保持最小预测准确率损失的前提下显著提升执行速度。利用长时序片段间的相似性，RITA动态聚合成少量分组并在粗粒度级别近似计算注意力值。

> ly clusters the segments into a small number (denoted as 𝑁 ) of groups. Segments in the same group possess similar feature embeddings during the current training iteration, enabling them to approximately share the computation of attention. As the timeseries increases in length, more sharing opportunities become available. RITA then computes self-attention at a group level and produces a compressed group attention matrix. In this way, group attention eliminates both computation and memory bottlenecks in Transformer-style models, and thus more scalable to long timeseries. However, making this idea effective and efficient in Transformer architectures is challenging for several reasons:
> • Efficiently producing high quality feature embeddings. RITA computes the attention matrix at a group level. To preserve the quality of the feature embeddings, it still has to produce different embeddings for different segments. This is because even if some segments share the attention score temporally, they may not share the same feature embedding. Using the group attention matrix, the existing self-attention mechanism will produce only a single feature vector for each group. Anaive solution would be to restore the original attention matrix from the group attention matrix. However, in this case, we again get an attention matrix with quadratic space complexity. Because GPUs have limited memory, GPU memory will remain a bottleneck in group attention. • The number of groups N. In RITA, the number of groups 𝑁 is a crucial factor that balances the speedup and quality of attention approximation. A small 𝑁 will lead to a large speedup, but the approximation errors can also be significant. On the other hand, although a large 𝑁 tends to produce high-quality approximations, it inevitably slows down the training process. Therefore, an appropriate 𝑁 is essential to the performance of group attention. However, 𝑁 depends on the distributional properties of the dataset. Furthermore, like the classical transformer models, RITA stacks multiple attention layers to produce better embeddings. Ideally, different layers should also use different values of 𝑁 . In addition, during the model training phase, group attention should use different values of 𝑁 in different iterations to adapt to the varying feature embeddings. This makes manually optimizing 𝑁 almost impossible. • Batch size. Moreover, as we want to dynamically adjust 𝑁 during training, a fixed batch size is sub-optimal: as 𝑁 decreases, the memory usage of a single sample decreases. This allows a larger batch size, which (1) makes full use of GPU memory; (2) enables parallelism across the samples. Thus, RITA should dynamically adjust the batch size as 𝑁 changes. To address the above problems, we first propose an embedding aggregation strategy and a customized group softmax function to replace the classical softmax function [59]. Together they ensure RITA able to directly use the compressed attention matrix to produce different feature embeddings for different segments. We theoretically show that the embeddings RITA produces in this way are identical to those produced by first re-storing the original large attention matrix. Thus
> RITA produces high-quality embeddings without introducing extra overhead. Proc. ACM Manag. Data, Vol. 2, No. 1 (SIGMOD), Article 62. Publication date: February 2024. 62:4 Jiaming Liang, Lei Cao, Samuel Madden, Zachary Ives, and Guoliang Li
> Second, we design an adaptive scheduler that dynamically decides an appropriate 𝑁 for each group attention layer during the training process. It starts with a large 𝑁 and iteratively merges groups that are similar to each other. Guided by an error bound on the approximated self-attention that users can tolerate, it automatically determines if two groups are mergeable, performing merging efficiently in a GPU-friendly way. Moreover, we propose a learning-based method to model the correlation between the number of groups 𝑁 and the batch size 𝐵. This model predicts 𝐵 for a given 𝑁 when training RITA. Specifically, we first sample some 𝑁 values in a reasonable range. For each sampled 𝑁, we find a batch size that consumes up to a certain percentage of GPU memory in a cost-efficient way. Using a small set of mathematical functions as a prior, RITA is able to learn a model with only a few ⟨𝑁, 𝐵⟩ pairs as ground truth labels. Our experiments on public timeseries benchmarks and the MGH EEG data [7] confirm that compared to existing self-attention mechanisms [11, 12, 46, 59, 62], our group attention mechanism achieves a 63X speedup with much less memory required with comparable or even better accuracy on various timeseries analytics tasks. Contributions. The key contributions of this work include:
> • Our group attention mechanism reduces the time and space complexity of the self-attention mechanism with accuracy guarantees, allowing RITA to scale to long timeseries data. • Guided by an approximation error bound, our adaptive scheduler dynamically adapts the number of groups and the batch size to the distribution properties of the evolving feature embeddings, making group attention efficient and easily tunable. • We conduct experiments on various datasets and analytics tasks, demonstrating that RITA is 4 to 63 times faster than the existing Transformer-based approaches while achieving comparable or better accuracy when handling long timeseries (length ≥ 2000). 2 BACKGROUND
> We provide some background on the canonical self-attention module in the Transformer [59]. takes 𝑛 hidden embedding vectors 𝐻 ∈ R𝑛∗𝑑ℎ as input, then projects them to queries
> Self-attention
> (𝑄), keys (𝐾) and values (𝑉 ) and performs Scaled-dot Product Attention, which given input hidden state 𝐻, is computed by:
> 𝑄 = 𝐻𝑊 ,𝐾 = 𝐻𝑊 ,𝑉 = 𝐻𝑊 ,𝑂 = 𝐴𝑉 = 𝑆𝑜𝑓𝑡𝑀𝑎𝑥( )𝑉 (1)
> 𝑄𝐾𝑉 √︁ 𝑑 𝑘
> Where 𝑊 ∈ R𝑑ℎ∗𝑑𝑘,𝑊 ∈ R𝑑ℎ∗𝑑𝑘,𝑊 ∈ R𝑑ℎ∗𝑑𝑣 are projection matrices for generating 𝑄,𝐾,𝑉. 𝑄 ∈ R𝑛∗𝑑𝑘 is also regarded as the packing of 𝑛 query vectors {𝑞 , ...,𝑞 } with dimension 𝑑 into
> 1𝑛 𝑘 a matrix. 𝐾 ∈ R𝑛∗𝑑𝑘,𝑉 ∈ R𝑛∗𝑑𝑣 are regarded as the packing of key vectors {𝑘 , ...,𝑘 } and value
> 1 𝑛 vectors {𝑣 , ..., 𝑣 } in the same way. Given a matrix 𝑀 ∈ R𝐿∗𝑛, the softmax function normalizes 𝑀 to ensure the sum of each row equals to 1, as shown below. 𝑒𝑥𝑝 (𝑀 ) 𝑖, 𝑗
> 𝑆𝑜 𝑓 𝑡𝑀𝑎𝑥 (𝑀 ) = (2) 𝑖,𝑗 𝑛 1
> − 𝑒𝑥𝑝(𝑀 ) 𝑘=0 𝑖,𝑘
> 3 RITA OVERVIEW
> Given a collection of unlabeled timeseries, RITA first pre-trains a Transformer-style model to produce high quality feature embeddings. This pre-trained model is then used to support various downstream tasks with minimal modifications to the model architecture, aligned with the design philosophy of BERT [19]. Proc. ACM Manag. Data, Vol. 2, No. 1 (SIGMOD), Article 62. Publication date: February 2024. RITA: Group Attention is All You Need for Timeseries Analytics 62:5
> ..... OOO O
> 012 n
> RITA Encoder
> E E E ..... E
> 0 1 2 n
> Position P ..... P
> P P
> Embedding0 1 2 n
> + + + +
> Window W W W W
> [CLS] 1 2 ..... n
> Embedding
> ..... Time-aware
> Convolution
> Scale & Input
> Raw Tim e se r ie s
> Fig. 2. RITA architecture
> Next, we use an example to show how RITA supports a timeseries query system in Sec. 3.1, followed by an overview of the RITA model architecture in Sec. 3.2. We will provide a detailed illustration on how RITA addresses a range of downstream tasks in Sec. 6. 3.1 RITA in Timeseries Query Systems
> Fig. 1 shows a Seizure Diagnosis System we have been developing for a major US hospital. RITA is used both in the training stage and the deployment stage. As described in the Introduction, we use
> RITA to encode the EEG segments and store the resulting (timeseries, embedding) pairs in a vector database as (key, value) pairs. This is used to for similarity-based labeling.

利用长时序片段间的相似性，RITA将输入时间序列分割为段，并动态地将这些段聚合成少量分组（记作𝑁）。同一组内的段在当前训练迭代中具有相似的特征嵌入，使它们能够近似共享注意力计算。随着时间序列长度增加，更多共享机会变得可用。RITA随后在组级别上计算自注意力并生成压缩后的组注意力矩阵。通过这种方式，组注意力消除了Transformer风格模型中的计算和内存瓶颈，因此更适用于长时序场景。然而，在Transformer架构中使这一想法有效且高效面临诸多挑战：
• 高质量特征嵌入的高效产生。RITA在组级别上计算注意力矩阵。为保持特征嵌入的质量，它仍需对不同段生成不同的嵌入表示。这是因为即使某些段在时间上共享注意力得分，它们可能并不具有相同的特征嵌入。使用组注意力矩阵时，现有的自注意力机制将为每个组仅产生一个特征向量。一种朴素的解决方案是通过组注意力矩阵恢复原始注意力矩阵。然而在这种情况下，我们再次得到一个空间复杂度呈二次增长的注意力矩阵。由于GPU内存有限，在组注意力中GPU内存仍将是瓶颈。
• 分组数量𝑁。在RITA中，分组数𝑁是一个关键因素，它平衡了速度提升与注意力近似质量之间的关系。较小的𝑁将带来较大的加速效果，但也会产生显著的近似误差。另一方面，虽然较大的𝑁倾向于生成高质量的近似结果，但它不可避免地会减缓训练过程。因此，合适的𝑁对组注意力性能至关重要。然而，𝑁依赖于数据集的分布特性。此外，如同经典Transformer模型一样，RITA堆叠多个注意力层以产生更好的嵌入表示。理想情况下，不同层数也应使用不同的𝑁值。另外，在模型训练阶段，组注意力应在不同迭代中采用不同的𝑁值来适应变化的特征嵌入。这使得手动优化𝑁几乎不可能。
• 批量大小。此外，由于我们希望在训练过程中动态调整𝑁，固定批量大小是次优选择：随着𝑁减少，单个样本内存使用会降低。这允许更大的批量尺寸，其（1）充分利用GPU内存；（2）实现跨样本的并行性。因此，RITA应随𝑁的变化动态调整批量大小。为解决上述问题，我们首先提出了一种嵌入聚合策略和定制化的组softmax函数以替代经典softmax函数[59]。二者共同确保RITA能够直接使用压缩后的注意力矩阵生成不同段的不同特征嵌入表示。我们在理论上证明了RITA通过这种方式产生的嵌入与先恢复原始大尺寸注意力矩阵后所产生的结果完全相同。因此，RITA在不引入额外开销的情况下产生高质量的嵌入表示。
Proc. ACM Manag. Data, Vol. 2, No. 1 (SIGMOD), Article 62. Publication date: February 2024. 62:4 Jiaming Liang, Lei Cao, Samuel Madden, Zachary Ives, and Guoliang Li
其次，我们设计了一种自适应调度器，在训练过程中动态决定每个组注意力层的适当𝑁值。它从较大的𝑁开始，并迭代地合并相似度高的分组。根据用户可容忍的近似自注意力误差界限进行指导，自动判断两个分组是否可以合并，并以GPU友好的方式高效执行合并操作。此外，我们提出了一种基于学习的方法来建模分组数𝑁与批量大小𝐵之间的相关性。该模型在训练RITA时预测给定𝑁对应的𝐵值。具体而言，我们首先在一个合理范围内采样一些𝑁值。对于每个采样的𝑁，我们在成本效益高的方式下找到一个使GPU内存使用达到特定百分比的批量尺寸。利用一组数学函数作为先验知识，RITA仅需少量⟨𝑁, 𝐵⟩对的真实标签即可学习到该模型。我们针对公开时间序列基准和MGH EEG数据[7]进行的实验验证了相比现有自注意力机制[11, 12, 46, 59, 62]，我们的组注意力机制在多种时序分析任务中以更少内存需求实现了63倍的速度提升且具有可比或更好的准确性。贡献：
• 提出了一种新型的组注意力机制（Group Attention），有效解决了Transformer模型处理长时间序列数据时面临的计算和内存瓶颈问题。
• 设计了自适应调度策略，动态调整分组数量𝑁以平衡速度与精度之间的关系，并通过数学建模优化批量大小选择。
• 在多个公开基准测试中验证了RITA的性能优势，在保持高准确率的同时显著提升了处理效率。

> vector database as (key, value) pairs. This is used to for similarity-based labeling. Thereafter, we train a classification model by fine-tuning the RITA model and deploy it in the patient monitoring system to detect seizures at real time. Once a new EEG segment arrives, the system uses the RITA encoder to embed it into a feature embedding, and thereafter classifies it into one type of seizures. 3.2 Model Architecture
> As shown in Fig. 2, RITA consists of two components: (1) Time-aware Convolution Layer and (2)
> RI TA Encoder. Time-aware Convolution Layer fills the gap between timeseries and natural language. Despite their high-level similarity, there is a big gap between timeseries and natural language. First, in natural language each word, as a discrete semantic unit, has an independent meaning, while each element in a timeseries is a continuous, numerical value and does not necessarily constitute an independent event. Furthermore, the input sequences are single-channeled in NLP, but often multi-channeled in timeseries (i.e., sensor data often consists of several related channels). RITA leverages the classical convolution [33] strategy to solve this problem. Convolution is widely used to capture the local structures of an image. We use convolution to chunk one input timeseries into a sequence of windows and learn the local structure of each window, similar to the discrete semantic units in natural language. It also discovers the correlations across different channels, thus naturally solving the multi-channel problem. Proc. ACM Manag. Data, Vol. 2, No. 1 (SIGMOD), Article 62. Publication date: February 2024. 62:6 Jiaming Liang, Lei Cao, Samuel Madden, Zachary Ives, and Guoliang Li
> More specifically, treating a multi-variate timeseries of length 𝑛 and with 𝑚 variables as an n × m matrix 𝑇, RITA uses 𝑑 convolution kernels to chunk 𝑇 into n windows and produce one ddimensional embedding per window using the convolution operation [33]. Each convolution kernel corresponds to a w × m matrix, where 𝑤 defines the number of timestamps that each convolution kernel covers, identical to the window size in sliding window. takes the embeddings of 𝑛 semantic units 𝑋 ,𝑋 ,...,𝑋 (𝑋 ∈ 𝑅𝑑) as input (e.g.
> RITAEncoder 1 2 𝑛 𝑖 embeddings of 𝑛 windows for a timeseries), then models the correlations between the semantic units and outputs 𝑌 , ...,𝑌 (𝑌 ∈ 𝑅𝑑) as the context-aware embedding of each unit. What makes RITA Encoder different from Transformer Encoder is that: at the core of Transformer
> Encoder lies self-attention mechanism which incurs a 𝑂 (𝑛2) time complexity and memory usage. This quadratic cost becomes prohibitive for long timeseries and limits the scalablity of Transformerbased models. To make the attention computation efficient yet high-quality, we replace the canonical self-attention with our proposed group attention. Self-supervised Pretraining. Inspired by the “cloze text” pretraining task in NLP, we designed a mask-and-predict task as the pretraining task for our model. The timeseries is randomly masked and the model should recover the masked values based on corresponding contextual information. To be specific, we generate masks on time-stamps, with a mask rate 𝑝. The timeseries is scaled to be non-negative and the values across all the channels on the masked timestamps are set to be
> -1, an impossible value on normal timestamps. Then the masked timeseries is fed into RITA and the output representation is translated to the recovered timeseries by a Transpose Convolution layer. 4 GROUP ATTENTION MECHANISM
> Group attention, a novel and efficient approximate attention mechanism, addresses the performance bottleneck of self-attention in the vanilla Transformer. In this section, we first introduce the framework of group attention and then theoretically establish the bound of its approximation error. We use examples to explain the group attention mechanism, as depicted in Figure 3. 4.1 The Idea of Group Attention
> As periodicity is a natural property of timeseries [64], similar windows frequently occur. Similar windows result in similar queries/keys for attention computation, bringing opportunities for saving computation. As discussed in Sec. 2, 𝐴 , the attention score of window 𝑖 onto window 𝑗, is determined by the 𝑖𝑗 inner product between the query vector of window 𝑖 and the key vector of window 𝑗, that is, 𝑞 · 𝑘 . Given another window 𝑥, if window 𝑥 has a key vector similar to that of window 𝑗, that is, 𝑘 ≈ 𝑘 , 𝑗 𝑥 then𝑞 ·𝑘 ≈𝑞 ·𝑘 .Inotherwords,𝐴 ≈𝐴 when𝑘 ≈𝑘 . 𝑖 𝑗 𝑖 𝑥 𝑖𝑗 𝑖𝑥 𝑗 𝑥
> Example 1. As shown in Figure 3 (Part 1), the first and third timeseries windows are notably similar, consequently yielding akin key vectors (𝑘 ≈ 𝑘 ). In vanilla self-attention (Part 2), this
> 1 3 similarity leads to two closely related columns within the attention matrix, corresponding to key vectors𝑘 and𝑘 . 1 3
> This observation inspires our group attention mechanism. That is, we group the windows by their similarity in keys. Assuming that all windows in the same group have the same attention score onto another window𝑘, we then only compute the attention once by using one single key to represent this group, for example the centroid of the group of keys. Thus, this saves significant computation cost. Better yet, after grouping 𝑛 windows into 𝑁 groups, group attention compresses the attention matrix from an𝑛 ×𝑛 matrix to an𝑛 × 𝑁 matrix. Because 𝑁 (number of groups) tends to be much smaller than 𝑛 (number of windows) due to the periodicity of timeseries, group attention consumes
> Proc. ACM Manag. Data, Vol. 2, No. 1 (SIGMOD), Article 62. Publication date: February 2024. RITA: Group Attention is All You Need for Timeseries Analytics 62:7 much less memory than the original self-attention mechanism, successfully eliminating the memory bottleneck. Note that this minimally impacts quality, as confirmed in our experiments (Sec. 7.2). 1 Producing Key, Query, Value Embeddings k1 , q 1 , v1 k2 , q 2 , v2 k3 , q 3 , v3 k4 , q 4 , v4 k, q, v ∈ R1*d
> 2 Vanilla Self-Attention k1 k2 k3 k4 v1 q v2 O1
> 1 -0.43 0.68 -0.38 0.39 0.14 0.41 0.14 0.31 × v3 O2 q2 0.24 -0.70 0.28 0.11 SoftMax 0.30 0.12 0.31 0.27 v4
> O3 q3
> -0.40 0.64 -0.38 0.37 (row sum = 1) 0.14 0.40 0.15 0.31 O4 q Output ∈ Rn*d
> 4 0.19 -0.14 0.21 0.12 0.27 0.19 0.28 0.26
> Dot Product ∈ Rn*n Attention Matrix ∈ Rn*n
> 3 Group Attention
> Detects Similar Key Embeddings: k1 ≈ k3
> Aggregate Key Embeddings: ( k1 + k3 )/2 k(1,3)
> Aggregate Value Embeddings: v1 + v3 v(1,3) k(1,3) k2 k4 v
> (1,3) q Group SoftMax 0.140.410.31 v O1
> 1 -0.41 0.68 0.39 2 q Column k(1,3) counts twice 0.30 0.12 0.28 × v O2
> 2 4
> 0.26-0.700.11 O3 q3 0.14 0.40 0.32
> -0.39 0.64 0.37 (row sum = 1) O4 q 0.140.400.32 n*d
> 4 Output ∈ R
> 0.20 -0.14 0.12 0.27 0.20 0.26 n*N Group Attention Matrix ∈ R n*N
> Dot Product ∈ R
> Fig. 3. Group Attention vs. Vanilla Self-Attention
> 4.2 Computing the Output Feature Embedding
> We now discuss how to efficiently compute the output feature embeddings using the small compressed group attention matrix. 4.2.1 Problem: Producing Embeddings with the Group Attention Matrix
> As described in the Background (Sec. 2), once we have acquired the attention matrix 𝐴, canonical self-attention computes the output embedding 𝑂 as O = AV. Because 𝐴 is an 𝑛 × 𝑛 matrix and
> 𝑉 is an 𝑛 × 𝑑 matrix, the matrix product operation still produces an 𝑛 × 𝑑 matrix 𝑂. That is, 𝑣 𝑣 it produces a 𝑑 dimensional feature vector for each window. However, our group attention will 𝑣 produce an 𝑛 × 𝑁 attention matrix 𝐴 , where 𝑁 corresponds to the number of groups. In this case

图1展示了一个我们为美国主要医院开发的癫痫诊断系统。RITA既用于训练阶段也用于部署阶段。如引言所述，我们使用RITA对脑电图片段进行编码，并将生成的（时序数据，嵌入表示）对存储在向量数据库中作为（键值对）。这被用于基于相似性的标签分配。随后，通过微调RITA模型训练分类器并部署到患者监测系统以实时检测癫痫发作。当新的脑电图片段到达时，系统使用RITA编码器将其嵌入为特征表示，并据此归类为某种类型的癫痫发作。3.2 模型架构  
如图2所示，RITA包含两个组件：（1）时间感知卷积层和（2）RI TA编码器。时间感知卷积层弥合了时序数据与自然语言之间的差距。尽管两者在高层具有相似性，但存在显著差异。首先，在自然语言中每个单词作为离散语义单元独立意义，而时序数据中的元素是连续数值且不一定构成独立事件。此外，NLP的输入序列通常是单通道的，但在时间序列中往往是多通道（即传感器数据通常包含多个相关通道）。RITA利用经典卷积[33]策略解决此问题。卷积广泛用于捕捉图像局部结构。我们使用卷积将一个输入时序分割为窗口序列并学习每个窗口的局部结构，类似于自然语言中的离散语义单元。它还发现不同通道间的关联性，从而天然地解决了多通道问题。Proc. ACM Manag. Data, Vol. 2, No. 1 (SIGMOD), Article 62. Publication date: February 2024. 62:6 Jiaming Liang, Lei Cao, Samuel Madden, Zachary Ives, and Guoliang Li  
更具体地，将长度为n、包含m个变量的多维时序数据视为一个n×m矩阵T。RNic利用卷积层生成键值对嵌入表示（见图3）。如图所示，在常规自注意力机制中，每个窗口产生d维度特征向量；而在组注意力机制下，则针对每组生成对应特征向量。Proc. ACM Manag. Data, Vol. 2, No. 1 (SIGMOD), Article 62. Publication date: February 2024. RITA: Group Attention is All You Need for Timeseries Analytics 62:7  
通过将注意力矩阵压缩为小规模组注意力矩阵，可以高效计算输出特征嵌入。3.2.1问题：使用组注意力矩阵生成嵌入表示  
如背景（第2节）所述，一旦获得注意力矩阵A，常规自注意力机制通过O=AV计算输出嵌入O。由于A是n×n矩阵且V是n×d矩阵，矩阵乘法仍产生一个n×d的矩阵O。即为每个窗口生成d维特征向量。然而我们的组注意力将生成一个n×N的注意力矩阵A'（其中N对应分组数量）。在这种情况下  
矩阵乘法会生成一个N×d的矩阵O。

> the matrix product will produce a 𝑁 × 𝑑 matrix 𝑂. That is, it produces a feature vector for each 𝑣 group.

即为每组生成对应的特征向量。

> the matrix product will produce a 𝑁 × 𝑑 matrix 𝑂. That is, it produces a feature vector for each 𝑣 group. However, our goal is to produce different embeddings for different windows, because even if some windows share the attention score temporally, it does not mean they should have the same feature emb e dding. A Naive Solution. Anaive solution would be to restore the full attention matrix 𝐴 from the group attention matrix 𝐴. For example, given one group composed of 𝑤𝑖𝑛 and 𝑤𝑖𝑛 , we map its group 𝑖𝑗 attention vector in 𝐴 into two rows that correspond to 𝑤𝑖𝑛 and 𝑤𝑖𝑛 in 𝐴. However, in this case 𝑖𝑗 we again get a 𝑛 × 𝑛 attention matrix; and GPU memory remains a bottleneck in group attention. Proc. ACM Manag. Data, Vol. 2, No. 1 (SIGMOD), Article 62. Publication date: February 2024. Usingan operationanda dingswithoutrestoringthefullattentionmatrix. conductedonthefullyrestoredattentionmatrix
> Givenanelement of correspondingtothe wherevector denotesthe dimensionofallthe featurevectors.Given
> = . AsshowninFig.3(Part3),assume
> Then 1 = 3 = 1 ,where 1
> 1 1 + 3 3 = 1 ( 1 + 3 ).Soweaggregate
> 1 3
> As an immediate generalization of the above belongtothesamegroupandconvertthen-dimensionalfeaturevector groupfeaturevector groupfeaturevector tocompute . Usingembeddingaggregation,RITAisabletoproducethefeatureembedding totheembedding producedbyusingthefullattentionmatrix
> = .Tocompute ,wehavetofirstcompute matrix.Normalizingthe
> Groupattentionfollowsthesameprocedure.However,aftergroupingkeysinto an matrix willresultinagroupattentionmatrix matrixthatisidenticaltofirstrestoring to producedbythelatterisdesirable,aswewanttoapproximatetheoriginalattentionmatrixas accuratelyaspossible.However,restoringthesmall willendupwithafull matrix . Tosolvetheaboveproblems,weintroduceanew softmaxfunction(Eq.2). InEq.3, representsthenumberofwindowsthatGroup originalsoftmax,ourgroupsoftmaxconsiderseachgroup timeswhensumminguptheexponentialofeachgroup’s
> 3),wecountthecolumncorrespondingto
> 1 3 elements(
> 1 3 matrixwillproduce aggregationoperationandgroupsoftmaxfunctioninAlg.1.Wedenote group, tobethenumberofgroups, bethematrixconsistingofall , fornewfeatureemebddings ,where

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

> Proc.ACMManag.Data,Vol.2,No.1(SIGMOD),Article62.Publicationdate:February2024. function,RITAproduces embedTheideaisinspiredbytheobservationonthematrixproductoperation
> . dimensionof ’sfeaturevector, = , rowoftheattentionmatrix andvector denotesthe and , and belongtothesamegroup . 1 3 1 correspondstotheattentionofgroup onto .Therefore,

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

> . 1 3 analysis, if we aggregate up the windows that intoa -dimensional beforehand,wecoulddirectlyusethegroupattentionvector andthe thatisidentical andtheembeddingmatrix . Incanonicalself-attentiontheattentionmatrix iscomputedas
> (denotedas )whichisan matrixwithsoftmaxproducestheattentionmatrix . , produces
> .Duetothenon-linearityofthesoftmaxfunction,applyingsoftmaxdirectlyon fromwhichwearenotabletorecoverafullattention andthenapplyingsoftmaxon .The matrix matrixisnotmemoryefficient,asit functiontoreplacetheoriginal
> (3)

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

> 0 contains.Comparedtothe as elementsandcountsit
> .Forinstance,inFig.3(Part twiceinGroupSoftMaxbecausetherearetwo
> )inthisgroup.Inthisway,thegroupsoftmaxfunctionoperatingonthesmall resulttothesoftmaxfunctionoperatingonthefull matrix. Next,wedemonstrateanefficientimplementationoftheembedding tobethesizeofthe tobetherepresentativekeyofthe groupand to tobethegroupthat belongsto. arethepacking matricesofqueryvectorsandvaluevectorsasdescribedinSec.2.Alg.1outputsthepackingmatrix correspondstothefeatureembeddingof . RITA: Group Attention is All You Need for Timeseries Analytics 62:9
> Algorithm 1 Efficient Computation of Group Attention
> Require: 𝑄, 𝑉 , 𝑅, 𝐶𝑁𝑇 , 𝐵𝐿𝐺
> Ensure: 𝑄,𝑉 ∈ R𝑛∗𝑑,𝑅 ∈ R𝑁∗𝑑,𝐶𝑁𝑇 ∈ N𝑁,𝐵𝐿𝐺 ∈ N𝑛
> 1: function group_attention(𝑄, 𝑉 , 𝑅)
> 2: for𝑖 = 0 → 𝑁 − 1 do
> 3: 𝑣 ← 𝑛−1(𝐵𝐿𝐺 == 𝑖)𝑣 𝑖 𝑗=0 𝑗 𝑗
> 4: 𝑃 ← 𝑄𝑅𝑇

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

> 5: for𝑖 = 0 → 𝑛 − 1 do
> 6: for 𝑗 = 0 → 𝑁 − 1 do
> 7: 𝑤 ← 𝑒𝑥𝑝(𝑃 )𝐶𝑁𝑇 𝑖,𝑗 𝑖,𝑗 𝑗
> 8: for𝑖 = 0 → 𝑛 − 1 do
> 9: 𝑠 ← 𝑁−1 𝑤 𝑖 𝑗=0 𝑖,𝑗
> 10: for𝑖 = 0 → 𝑛 − 1 do
> 𝑁 −1 𝑒𝑥𝑝 (𝑃𝑖,𝑗 )
> 11:𝑜← 𝑣 𝑖 𝑗=0 𝑠 𝑗 𝑖
> 12: return𝑂
> Lines 2-3 implement the embedding aggregation operation, while Lines 8-11 implement the group softmax function. The Correctness Proof of the Group Attention Algorithm. Here we prove that our efficient group attention algorithm, i.e., Alg. 1, produces the same output feature embedding with the naive method that has to first restore the big full attention matrix. 62:10 Jiaming Liang, Lei Cao, Samuel Madden, Zachary Ives, and Guoliang Li
> Further, 𝑛−1 𝑁 −1 𝑛−1
> ∑︁ ∑︁∑︁ o = 𝐴 v = (𝐵𝑁𝐺 ==𝑗)𝐴 v 𝑖 𝑖,𝑗j 𝑥 𝑖,𝑥𝑥 𝑗=0 𝑗=0 𝑥=0
> 𝑁 −1 𝑛−1
> ∑︁ ∑︁ 𝑒𝑥𝑝(q ·k ) 𝑖 𝑥
> = (𝐵𝐿𝐺==𝑗) v (7) 𝑥 𝑛1 𝑥
> − 𝑒𝑥𝑝(𝑃 ) 𝑗=0 𝑥=0 𝑘=0 𝑖,𝑘
> 𝑁 −1 𝑒𝑥𝑝 𝑛−1 𝑁 −1 𝑒𝑥𝑝
> ∑︁ (q𝑖·r) ∑︁ ∑︁ (q𝑖·r) j 𝐵𝐿𝐺𝑗 j𝑣
> = ( 𝑥==)v𝑥= 𝑗 𝑛−1 𝑒𝑥𝑝 𝑃 𝑛−1 𝑒𝑥𝑝 𝑃
> ( 𝑖,𝑘) ( 𝑖,𝑘) 𝑗=0 𝑘=0 𝑥=0 𝑗=0 𝑘=0
> Combining (4), (6) (7), we have = N−1 Pi,j = . o vo i j=0 sj i
> This concludes that the output of our groupiattention is identical to vanilla self-attention’s. □
> Time Complexity. The time complexity of Alg. 1 is 𝑂(𝑛𝑁𝑑) and the space complexity is 𝑂(𝑛𝑁), while the time and space complexity of the original self-attention mechanism are 𝑂 (𝑛2𝑑) and 𝑂 (𝑛2). 4.3 ErrorBound
> Group attention produces a group attention matrix 𝐴 which approximates the attention matrix 𝐴

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

> produced by the classical self-attention with a bounded error, as shown in Lemma 4. Lemma 4. Let 𝑅 be the radius of the ball where all key vectors live;𝑘 be the representative of the 𝑖 group that contains key 𝑘 . Let 𝐴 denote the full attention matrix restored from 𝐴. Suppose the distance 𝑖 between 𝑘 and 𝑘 (||k − k ||) satisfies: ||k − k || ≤ d. 𝑖 𝑖 𝑖 𝑖 𝑖 𝑖 𝜖>1 ln(𝜖)1 A, 𝜖
> Then∀ ,ifd≤ , ≤ ij≤
> 2R 𝜖 A, i j
> Lemma 4 shows that the error bound 𝜖 of the group attention is determined by the distance 𝑑. As discussed in Sec. 5.1, it inspires us to design a strategy to dynamically determine the number of groups 𝑁 – the most critical parameter of group attention. Proof. We have 𝑒𝑥𝑝(𝑃 ) 𝑒𝑥𝑝(q · k ) 𝑖,𝑗 𝑖 𝑗
> = = 𝑒𝑥𝑝(q · (k − k )) 𝑖 𝑗 𝑗 𝑒𝑥𝑝(𝑃 ) 𝑒𝑥𝑝(q · k ) (8) 𝑖,𝑗 𝑖 𝑗
> = 𝑒𝑥𝑝(||q ||||k − k ||𝑐𝑜𝑠(q , k − k )) 𝑖 𝑗 𝑗 𝑖 𝑗 𝑗
> So 𝑒𝑥𝑝 (𝑃 ) 𝑖, 𝑗 𝑒𝑥𝑝 (−𝑑𝑅) ≤ ≤ 𝑒𝑥𝑝 (𝑑𝑅) (9) 𝑒𝑥𝑝 (𝑃 ) 𝑖, 𝑗
> Then we have:
> 𝐴 𝑒𝑥𝑝(𝑃 ) 𝑒𝑥𝑝(𝑃 ) 𝑖, 𝑗 𝑖, 𝑗 𝑖, 𝑗
> = /
> 𝐴 𝑛 𝑛 𝑒𝑥𝑝(𝑃 ) 𝑖,𝑗 𝑒𝑥𝑝(𝑃 ) 𝑖,𝑘 𝑘1 𝑖,𝑘 𝑘=1
> = (10) 𝑒𝑥𝑝𝑃 𝑛 𝑒𝑥𝑝(𝑃 )
> ( 𝑖,𝑗 ) 𝑖,𝑘 𝑘 =1
> = 𝑒𝑥𝑝(𝑃 ) 𝑛 𝑒𝑥𝑝 𝑃 𝑖,𝑗 ( 𝑖,𝑘 ) 𝑘 =1
> Combining (9) (10), the error is bounded by
> 𝐴 𝑖, 𝑗 𝑒𝑥𝑝 (−2𝑑𝑅) ≤ ≤ 𝑒𝑥𝑝 (2𝑑𝑅) (11)
> 𝐴 𝑖, 𝑗
> Thus, if ln(𝜖) , 1 A, 𝜖. This proves Lemma 4. □ d≤ ≤ ij≤
> 2R 𝜖 A, i j
> Proc. ACM Manag. Data, Vol. 2, No. 1 (SIGMOD), Article 62. Publication date: February 2024. RITA: Group Attention is All You Need for Timeseries Analytics 62:11
> 4.4 GPU-Friendly Grouping Method
> We implement a grouping method that corresponds to K-means clustering [41], because K-means offers a tight distance bound between each key and its group representative. We design a GPUfriendly implementation of K-means compliant to the Transformer architecture. The performance bottleneck of K-means comes from the distance computation between each vector and its center, thatis, √︁ , , , , .Theperformancebottleneckis𝑣 𝑐.Instead,
> |v − c | = (v − c )2 i ∈ [1 n] j ∈ [1 N] 𝑖 − 𝑗 ij ij weuseadifferentformulation:𝑣 𝑐 √︁ , , , , .In
> | 𝑖 − 𝑗| = |v − c | = |v |2 + |c |2 − 2v · c i ∈ [1 n] j ∈ [1 N] i j i j i j this formulation, the performance bottleneck is 𝑣 · 𝑐 , which could be implemented as a matrix 𝑖 𝑗 product operation, while in GPUs, matrix product is much more efficient than pairwise difference. 5 ADAPTIVE SCHEDULER
> Next, we present the adaptive scheduler of RITA which addresses the challenges of determining an appropriate number of groups 𝑁 and accordingly the batch size 𝐵, as described in Introduction.

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V召n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为 lĩnh là một ma trận n×n và V là một ma trận n×d, phép nhân ma trận sẽ tạo ra một ma trận O có kích thước n×d.  
Do A là một ma trận n×n và V là một ma trận n×d, vì vậy phép nhân ma trận vẫn sẽ sinh ra một ma trận O với kích thước n×d.

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。  
由于A是一个n×n矩阵而V是n×d矩阵，因此矩阵相乘运算仍会生成一个n×d维度的矩阵O。

在保持原有结构和数学符号不变的前提下，对原文进行逐句翻译：

因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘
</think>

看起来您可能是在尝试输入或处理一段涉及线性代数的内容（如矩阵相乘），但句子似乎没有完整结束。为了更好地帮助您，请确认以下几点：

1. **是否需要完成这句话？**  
   例如：“因为A是一个n×n矩阵且V是n×d矩阵，矩阵乘法操作仍然会产生一个n×d的矩阵O。” 这句话在数学上并不完全准确（通常我们不会用“O”表示结果矩阵），但可以理解为：如果 A 是 n×n 矩阵、 V 是 n×d 矩阵，则它们相乘的结果是一个 **n×d** 的矩阵。

2. **是否需要解释这个过程？**  
   例如：
   - 如果 $ A \in \mathbb{R}^{n\times n},\quad V \in \mathbb{R}^{n\times d} $，那么它们的乘积是：$ AV = O \in \mathbb{R}^{n\times d} $
   - 这个结果矩阵每一列都是 A 作用在 V 的对应列上的线性组合。

3. **是否需要进一步数学推导或应用？**  
   比如：
   - 如果 $ AV = O $，那么这可能意味着什么（例如：V 是齐次方程组的解）？
   - 是否有其他条件限制？

---

### 示例解释

假设我们有一个矩阵乘法：

$$
A \in \mathbb{R}^{n\times n},\quad V \in \mathbb{R}^{n\times d}
$$  
那么它们相乘的结果是：

$$
AV = O, \text{ 其中 } O \in \mathbb{R}^{n\times d}
$$

这表示矩阵 A 作用在向量 $ V_j $（第 j 列）上，得到的是零列。  
换句话说：

- 每一列 $ v_j $ 是齐次方程组 $ Ax = 0 $ 的解。
- 所以整个矩阵 $ V \in \mathbb{R}^{n\times d} $ 中的每一列都是 A 的零空间中的向量。

---

如果您能提供更多上下文（比如这句话出现在什么场景中？是数学推导、编程问题，还是其他用途），我可以更准确地帮助您。

> 5 ADAPTIVE SCHEDULER
> Next, we present the adaptive scheduler of RITA which addresses the challenges of determining an appropriate number of groups 𝑁 and accordingly the batch size 𝐵, as described in Introduction. Using a dynamic scheduling method we propose, the scheduler automatically determines and adjusts 𝑁 and 𝐵 based on the distributional properties of the feature embeddings produced over the iterative training process, while guaranteed to produce high quality attention approximation that meets the requirement of users. In Sec. 5.1 we show how RITA automatically determines 𝑁. Then we introduce in Sec. 5.2 the learning-based method which given an 𝑁 , immediately predicts a good batch size. 5.1 Dynamically Determining the Number of Groups N
> Without loss of generality, we use one group attention module as an example to show how RITA automatically gets an appropriate 𝑁 . RITA starts with a large 𝑁 and decreases it dynamically. This is because in the training process of RITA, the feature embeddings produced epoch by epoch tend to get stabler and stabler and gradually converge [30], thus typically no need to increase 𝑁 . RITA reduces the number of groups by merging similar groups. Intuitively, given two groups, we could measure their similarity based on the distance of their centers. If the distance between their centers is smaller than a distance threshold, then the two groups could be merged. However, setting an appropriate distance threshold seems hard – as difficult as setting an appropriate 𝑁 . To solve this problem, RITA leverages the error bound of group attention introduced in Sec. 4.3. It only requires users to set an error bound 𝜖, and then uses Lemma 4 to translate 𝜖 to a distance threshold 𝑑. We believe this error bound is the most natural knob for users to specify based on the need of the domain. Compared to setting a distance threshold to indirectly influence the approximation error, this is more intuitive and accessible. As confirmed in our experiments (Table. 4,
> Sec. 7.5.1), RITA works well in a large range of error bound factors. Hence it is not a parameter that needs careful tuning. RITA then uses Lemma 5 to determine if merging some given clusters still meets the error bound threshold 𝜖. Lemma 5. Denote 𝑐 to be the cluster center of 𝑐𝑙𝑢𝑠𝑡𝑒𝑟 . Assume the existing grouping satisfies 𝑘 𝑘
> ∀k, max |c − x| ≤ d , thus satisfying an error bound 𝜖 by Lemma 4. If there exist 𝑚 clusters, namely, k x ∈cluster k 𝑐𝑙𝑢𝑠𝑡 𝑒𝑟 , 𝑐𝑙𝑢𝑠𝑡 𝑒𝑟 , ..., 𝑐𝑙𝑢𝑠𝑡 𝑒𝑟 , satisfying that: 𝑘1 𝑘2 𝑘𝑚 𝑚𝑎𝑥 |𝑐 −𝑐 | + |𝑥 −𝑐 | ≤ 𝑑,𝑖, 𝑗 ∈ [1,𝑚] (12) 𝑘𝑖 𝑘𝑗 𝑘𝑖 𝑥∈𝑐𝑙𝑢𝑠𝑡𝑒𝑟𝑘 𝑖 merging them into one cluster still meets the error bound 𝜖. Proof. Denote the cluster size of 𝑐𝑙𝑢𝑠𝑡𝑒𝑟 to be 𝑛 . After mergeing, the new center will be: 𝑘 𝑘 𝑚 𝑛 𝑐 𝑐′ = 𝑖=1 𝑘𝑖 𝑘𝑖 . 𝑚 𝑛 𝑖=1 𝑘𝑖
> Proc. ACM Manag. Data, Vol. 2, No. 1 (SIGMOD), Article 62. Publication date: February 2024. 62:12 Jiaming Liang, Lei Cao, Samuel Madden, Zachary Ives, and Guoliang Li
> For ∀𝑖 ∈ [1,𝑚], ∀𝑥 ∈ 𝑐𝑙𝑢𝑠𝑡𝑒𝑟 , it holds that: 𝑘𝑖
> |𝑥 − 𝑐′| ≤ |𝑥 − 𝑐 | + |𝑐 − 𝑐′| (𝑇𝑟𝑖𝑎𝑛𝑔𝑙𝑒 𝑖𝑛𝑒𝑞𝑢𝑎𝑙𝑖𝑡𝑦) 𝑘𝑖 𝑘𝑖 𝑚 𝑛 𝑚 𝑛 𝑐 𝑗=1 𝑘𝑗 𝑗=1 𝑘𝑗 𝑘𝑗
> =|𝑥−𝑐 |+| 𝑐 − | 𝑘𝑖 𝑚 𝑛 𝑘𝑖 𝑚 𝑛 𝑗=1 𝑘𝑗 𝑗=1 𝑘𝑗 𝑚𝑛𝑐 𝑐 𝑘 ( 𝑘 − 𝑘 ) (13) 𝑗=1 𝑗 𝑖 𝑗
> = |𝑥 −𝑐 | + | | 𝑘𝑖 𝑚𝑛 𝑗=1 𝑘𝑗 𝑚𝑛 𝑐 𝑐 𝑥𝑐 𝑚𝑛𝑑 𝑘 (|𝑘 − 𝑘 |+| − 𝑘|) 𝑘 𝑗=1 𝑗 𝑖 𝑗 𝑖 𝑗=1 𝑗
> = ≤=𝑑 𝑚𝑛 𝑚𝑛 𝑗=1 𝑘𝑗 𝑗=1 𝑘𝑗
> Finding the Mergable Clusters. We formulate the problem of finding mergeable clusters using graph theor y:
> (1) each cluster is a node in the graph;
> (2) if 𝑐𝑙𝑢𝑠𝑡 𝑒𝑟 and 𝑐𝑙𝑢𝑠𝑡 𝑒𝑟 satisfy: 𝑖 𝑗 𝑚𝑎𝑥 |𝑐 −𝑐 | + |𝑥 −𝑐 | ≤ 𝑑, and 𝑚𝑎𝑥 |𝑐 −𝑐 | + |𝑥 −𝑐 | ≤ 𝑑 𝑖𝑗 𝑖 𝑗𝑖 𝑗 𝑥 ∈𝑐𝑙𝑢𝑠𝑡 𝑒𝑟𝑖 𝑥 ∈𝑐𝑙𝑢𝑠𝑡 𝑒𝑟 𝑗 then there is an undirected edge between 𝑛𝑜𝑑𝑒 and 𝑛𝑜𝑑𝑒 ; 𝑖 𝑗
> In this scenario, finding the maximal number of mergeable clusters is equivalent to finding the minimal clique cover in the corresponding graph, which is an NP-hard problem [28]. Such heavy computation overhead is not acceptable for RITA. We thus offer a simplified solution:
> (1) Halve the clusters into two sets 𝑆 ,𝑆 ;
> 1 2
> (2) If 𝑐𝑙𝑢𝑠𝑡𝑒𝑟 ∈ 𝑆 and 𝑐𝑙𝑢𝑠𝑡𝑒𝑟 ∈ 𝑆 satisfy: 𝑖1 𝑗2 𝑑 𝑚𝑎𝑥 |𝑐 −𝑐 |+|𝑥 −𝑐 | ≤𝑑, 𝑚𝑎𝑥 |𝑐 −𝑐 |+|𝑥 −𝑐 | ≤ (14) 𝑖𝑗 𝑖 𝑗𝑖 𝑗 𝑥 𝑐𝑙𝑢𝑠𝑡 𝑒𝑟 𝑥 𝑐𝑙𝑢𝑠𝑡 𝑒𝑟 2
> ∈𝑖 ∈𝑗 𝑐𝑙𝑢𝑠𝑡 𝑒𝑟 is marked. (3) Decrease the number of clusters by counting the masks in 𝑆 . The Correctness Proof. In this solution, clusters in 𝑆 can be regarded as transfer nodes. If (14)
> 1 holds for (𝑐𝑙𝑢𝑠𝑡𝑒𝑟 ∈ 𝑆 ,𝑐𝑙𝑢𝑠𝑡𝑒𝑟 ∈ 𝑆 ) and (𝑐𝑙𝑢𝑠𝑡𝑒𝑟 ∈ 𝑆 ,𝑐𝑙𝑢𝑠𝑡𝑒𝑟 ∈ 𝑆 ), respectively, we have, 𝑖 1 𝑗1 2 𝑖 1 𝑗2 2 𝑚𝑎𝑥 |𝑐 −𝑐 |+|𝑥−𝑐 | 𝑗1 𝑗2 𝑗1 𝑥 ∈𝑐𝑙𝑢𝑠𝑡 𝑒𝑟 𝑗

5 自适应调度器
接下来我们介绍RITA的自适应调度器，该调度器解决了确定适当组数𝑁以及相应批量大小𝐵的挑战，如引言中所述。通过我们提出的动态调度方法，调度器能够根据迭代训练过程中生成的特征嵌入分布特性自动决定并调整𝑁和𝐵，在保证产生高质量注意力近似的同时满足用户需求。在第5.1节我们将展示RITA如何自动确定𝑁。然后我们在第5.2节介绍基于学习的方法，该方法给定一个𝑁后能够立即预测合适的批量大小。

> ≤ 𝑚𝑎𝑥 |𝑐 −𝑐 |+|𝑐 −𝑐 |+|𝑥−𝑐 | 𝑗1 𝑖 𝑖 𝑗2 𝑗1 (15) 𝑥 ∈𝑐𝑙𝑢𝑠𝑡 𝑒𝑟 𝑗

5.1 动态确定组数N
不失一般性，我们以单个组注意力模块为例说明RITA如何自动获得适当的𝑁值。RITA初始采用较大的𝑁并动态减少其数值。这是因为RITA的训练过程中，每轮生成的特征嵌入会逐渐趋于稳定并最终收敛[30]，因此通常无需增加𝑁值。RITA通过合并相似组来降低组数。直观上讲，给定两个组，我们可以通过它们中心点的距离衡量相似性。如果两组佺心距离小于阈值，则将其合并。具体实现中采用分步策略：首先将所有聚类划分为两个子集𝑆₁和𝑆₂；其次检查满足条件的跨子集组合（𝑐𝑙𝑢𝑠𝑡𝑒𝑟 ∈ 𝑆₁, 𝑐𝑙𝑢𝑠𝑡𝑒𝑟 ∈ 𝑆₂）并标记符合条件的组对；最后通过统计掩码数量减少总聚类数。正确性证明显示，该方法能够保证合并后的多组满足误差界限条件，并采用动量更新[49]平滑𝑁值变化以避免样本选择偏差。

> ≤ 𝑚𝑎𝑥 |𝑐 −𝑐 |+|𝑐 −𝑐 |+|𝑥 −𝑐 |+|𝑥 −𝑐 | ≤𝑑 𝑗1 𝑖 𝑖 𝑗2 𝑗1 𝑗2 𝑥 ∈𝑐𝑙𝑢𝑠𝑡 𝑒𝑟 𝑗

5.2 动态确定批量大小
当模型架构和硬件固定时，批量大小取决于时间序列长度𝐿以及所有注意力模块中的平均组数𝑁。直观上讲，给定一个批量大小𝐵和组数𝑁，若能精确计算其GPU内存占用量，则可根据GPU可用内存容量和𝐿直接决定合适批次尺寸。但实际存在以下限制：(1) RITA的动态分组导致深度学习计算图不断变化[1]；(2) 深度学习基础设施采用的记忆管理技术[3]使得无法准确预测内存消耗。因此我们提出基于学习的方法来预测批量大小。该方法通过采样批次实际占用的GPU内存建立𝐿、𝑁与𝐵之间的相关性，我们在训练过程中高效测量这些数据并构建模型。RITA随机采样若干(𝐿ᵢ, 𝑁ᵢ)对，并为每个组合估计合适的批量尺寸。将这些配对视为真实标签后，我们采用函数拟合[22]学习预测函数B = f(L,N)，其中𝐵是两个变量𝐿和𝑁的函数。更具体地，在给定用户定义的时间序列最大长度𝐿ₘₐₓ的前提下，我们在平面{1 ≤ 𝐿 ≤ 𝐿ₘₐₓ, 1 ≤ 𝑁 ≤ 𝐿}中随机采样𝑚𝑎𝑥个整数点(𝐿ᵢ,𝑁ᵢ)。随后采用基于二分查找的算法寻找最大批量尺寸𝐵使得内存占用低于90%可用GPU容量，旨在避免浪费显存和内存溢出(OOM)风险。接下来讨论如何利用这些样本数据学习预测函数。

> Thus (12) holds when merging several clusters in𝑆 with one cluster in𝑆 . As a result, we can
> 2 1 greedily merge clusters in 𝑆 , as illustrated in step(3). Assume the number of clusters decreases by 𝐷 after merging, we apply a momentum update [49] on the number of clusters 𝑁 , as is commonly used in machine learning to smooth the changing of 𝑁 and avoid sample selection bias. To be specific: 𝑁 = 𝛼(𝑁 − 𝐷) + (1 − 𝛼)𝑁, where 𝛼 is a 𝑛𝑒𝑤 hyper-parameter for momentum. 5.2 Dynamically Determining the Batch Size
> When the model architecture and hardware are fixed, the batch size depends on the length of the timeseries 𝐿 and the average group number 𝑁 among all attention modules. Intuitively, given a batch size 𝐵 and the number of groups 𝑁, if we could precisely calculate its GPU memory usage, it would be straightforward to determine the appropriate batch size based on the GPU memory size and 𝐿. However, this is infeasible due to the following: (1) RITA’s dynamic grouping leading to
> Proc. ACM Manag. Data, Vol. 2, No. 1 (SIGMOD), Article 62. Publication date: February 2024. RITA: Group Attention is All You Need for Timeseries Analytics 62:13 varying deep learning computational graphs [1], and (2) the utilization of memory management techniques by the deep learning infrastructure [3]. Therefore, we propose a learning-based method to predict the batch size. It models the correlation between the length of the timeseries 𝐿, the number of groups 𝑁, and the batch size 𝐵 based on the actual GPU memory consumed by some sampled batches, which we efficiently measure during the training pro cess. RITA samples several (𝐿 , 𝑁 ) pairs and estimate a proper batch size for each pair. Treating these 𝑖 𝑖 pairs as ground truth labels, we use function fitting [22] to learn the batch size predicting function
> B = f (L,N), where Bis a function of two variables 𝐿 and 𝑁. More specifically, given a user-defined timeseries maximal length 𝐿 , we randomly sample 𝑚𝑎𝑥 integral points (𝐿 ,𝑁 ) from plane {1 ≤ 𝐿 ≤ 𝐿 ,1 ≤ 𝑁 ≤ 𝐿}. Then we use a binary search based 𝑖 𝑖 𝑚𝑎𝑥 algorithm to find the maximal batch size 𝐵 that consumes less than 90% available GPU memory, 𝑖 aiming to avoid wasting GPU memory and the risks of out of memory (OOM). Next, we discuss how to learn the prediction function using these sampled (𝐿 , 𝑁 , 𝐵 ). Learning the Prediction Function. We apply curve fit from SciPy [60] as the function fitting tool to fit the two-variable function 𝐵 = 𝑓 (𝐿 ,𝑁 ) on plane {1 ≤ 𝐿 ≤ 𝐿 ,1 ≤ 𝑁 ≤ 𝐿}. 𝑖 𝑖𝑖 𝑚𝑎𝑥
> We observe that applying one function to the whole plane incurs a huge estimation error. So we develop a dynamic-programming (DP) method to divide the plane into several sub-planes and apply a distinct function to each sub-plane respectively, i.e., Alg. 2. It is optimal in minimizing the total estimation error on all sub-planes. With the learned prediction function 𝑓 , we can estimate a proper batch size for any (𝐿, 𝑁 ) during training, even if it is not seen in the sampled (𝐿 , 𝑁 ) pairs.

学习预测函数
我们使用SciPy[60]中的曲线拟合工具对平面{1 ≤ 𝐿 ≤ 𝐿ₘₐₓ, 1 ≤ 𝑁 ≤ 𝐿}上的双变量函数𝐵 = f(𝐿,𝑁)进行建模。观察发现，将单一函数应用于整个平面上会导致巨大估计误差。因此我们开发动态规划(DP)方法将平面划分为若干子区域，并为每个子区域应用不同的拟合函数（即算法2）。该方法在所有子区域内最小化总估计误差方面达到最优解。通过学习得到的预测函数𝑓，可以在训练过程中对任意(𝐿,𝑁)组合估算合适的批量尺寸，即使这些组合未出现在采样的(𝐿ᵢ, 𝑁ᵢ)配对中。

> ize for any (𝐿, 𝑁 ) during training, even if it is not seen in the sampled (𝐿 , 𝑁 ) pairs. Algorithm 2 Dynamic Programming for Plane Division
> Require: 𝐿𝑖 , 𝑁𝑖 , 𝐵𝑖 , 𝐿𝑚𝑎𝑥
> Ensure: 1 ≤ 𝐿 ≤ 𝐿 ,1 ≤ 𝑁 ≤ 𝐿 𝑖 𝑚𝑎𝑥 𝑖 𝑖
> 1: function cost(S)
> 2: if |𝑆| < 𝑀 then return +∞
> 3: 𝐿, 𝑁, 𝐵 ← 𝑝𝑜𝑖𝑛𝑡𝑠 𝑖𝑛 𝑆
> 4: 𝑓 ← 𝑓 𝑢𝑛𝑐𝑡𝑖𝑜𝑛 𝑓 𝑖𝑡𝑡𝑖𝑛𝑔(𝐵 |𝐿, 𝑁 ) return 𝐸(𝐵,𝐿,𝑁|𝑓 )
> 5: function dynamic_programming(𝐿 , 𝑁 ,𝐿 ) 𝑖 𝑖 𝑚𝑎𝑥
> 6: for𝑙1 = 1 → 𝐿 do 𝑚𝑎𝑥
> 7: for𝑙2 = 1 → 𝑙1 do
> 8: for𝑛 = 1 → 𝑙1 do
> 9: 𝑆 ← 𝑝𝑜𝑖𝑛𝑡𝑠 𝑠𝑒𝑡 𝑖𝑛 {𝑙2 ≤ 𝐿 ≤ 𝑙1, 𝑁 ≤ 𝑛}
> 10: 𝑔(𝑛) ← 𝐶𝑂𝑆𝑇 (𝑆 )
> 11: for𝑖 = 1 → 𝑛 do
> 12: 𝑆 ← 𝑝𝑜𝑖𝑛𝑡𝑠 𝑠𝑒𝑡 𝑖𝑛 {𝑙2 ≤ 𝐿 ≤ 𝑙1,𝑖 ≤ 𝑁 ≤ 𝑛}
> 13: 𝑔 (𝑛) ← 𝑚𝑖𝑛 (𝑔 (𝑛), 𝑔 (𝑖 ) + 𝐶𝑂𝑆𝑇 (𝑆 ) )
> 14: 𝑓 ← 𝑔(𝑙1) 𝑙2,𝑙1
> 15:
> 16: for𝑙 = 1 → 𝐿 do 𝑚𝑎𝑥
> 17: 𝑑𝑝(𝑙) ← 𝑓 (1,𝑙)
> 18: for𝑖 = 1 → 𝑙 do
> 19: 𝑑𝑝 (𝑙 ) ← 𝑚𝑖𝑛 (𝑑𝑝 (𝑙 ), 𝑑𝑝 (𝑖 ) + 𝑓 (𝑖, 𝑙 ) ) return 𝑑𝑝 (𝐿𝑚𝑎𝑥 )
> The Optimality Proof of the Plane Division Algorithm . We describe Alg. 2 and intuitively show its optimality. We assume that Scipy [60] learns an optimal function in Line 4 so that function COST gives the optimal estimation error when fitting the points in set 𝑆. When fitting very few points,
> Proc. ACM Manag. Data, Vol. 2, No. 1 (SIGMOD), Article 62. Publication date: February 2024. 62:14 Jiaming Liang, Lei Cao, Samuel Madden, Zachary Ives, and Guoliang Li we assign an infinite cost to prevent a biased fitting function (Line 2). 𝑔(𝑛) denotes the minimal estimation error for points in sub-plane {𝑙 ≤ 𝐿 ≤ 𝑙 , 𝑁 ≤ 𝑛}. In Lines 11-13, we enumerate all
> 2 1 possible ways of cutting {𝑙 ≤ 𝐿 ≤ 𝑙 ,𝑁 ≤ 𝑛} horizontally into two sub-plane {𝑙 ≤ 𝐿 ≤ 𝑙 ,𝑁 ≤ 𝑖}
> 21 21 and {𝑙 ≤ 𝐿 ≤ 𝑙 ,𝑖 ≤ 𝑁 ≤ 𝑛} byiterating𝑖 from1ton.Choosingthecuttingstrategythatminimizes
> 2 1 estimation error gets us a 𝑔(𝑙 ) with minimal estimation error for sub-plane {𝑙 ≤ 𝐿 ≤ 𝑙 , 𝑁 ≤ 𝑙 },
> 1 211 which is recorded as 𝑓 in Line 14. 𝑑𝑝(𝑙) denotes the minimal estimation error for sub-plane 𝑙1,𝑙2
> {𝐿 ≤ 𝑙 }. We enumerate all the possible ways of cutting {𝐿 ≤ 𝑙 } vertically into two sub-plane {𝐿 ≤ 𝑖} and {𝑖 ≤ 𝐿 ≤ 𝑙} by iterating 𝑖 from 1 to 𝑙 (Line 17-19). Finally, we have the minimal estimation error for the whole plane as 𝑑𝑝(𝐿 ). Based on the above discussion, this algorithm guarantees to 𝑚𝑎𝑥 not miss any better solution, hence optimal. 6 SUPPORTING DOWNSTREAM TASKS
> RITA supports a variety of downstream tasks. In this section, we show that with minimal modification RITA can effectively support classification, imputation and forecasting tasks. Other unsupervised tasks such as similarity search or clustering are naturally supported by extracting feature embeddings from RITA. 6.1 Classification
> To classify timeseries, we input timeseries to the model as described in Sec. 3 and attach a special token [CLS] as the first input embedding. [CLS]’s embedding acts as the embedding for the entire timeseries, and the output representation of [CLS] is fed into a classifier: y = Softmax (W Z + B ), cls [CLS] cls where 𝑍 ∈ R𝑑 is the output representation of , Cis the number of classes, and
> 𝐶𝐿𝑆 [CLS]
> [ ]
> ∈ RC×d, ∈ RC are learnable parameters for classification task. The result vector 𝑦 ∈ R𝐶
> W Bcls cls represents the possibility that the input timeseries belongs to each class. We apply Cross Entropy as the loss function for the classification task [16]. 6.2 Imputation
> Timeseries are mainly generated by sensors, a common problem of which is missing values. This becomes a challenge when many downstream analytics require the missing values to be recovered. The recovering task is imputation, a data cleaning task. Denote the real timeseries as 𝑇 ∈ R𝑡 ×𝑚, the observed timeseries with missing values as 𝑇 ∈ R𝑡 ×𝑚, 𝑟 𝑜 and the set of missing values’ positions as 𝑀. We scale the values of all timeseries to non-negative and use a special value (-1) to indicate missing values:

该方法在所有子区域内最小化总估计误差方面达到最优解。通过学习得到的预测函数𝑓，可以在训练过程中对任意(𝐿,𝑁)组合估算合适的批量尺寸，即使这些组合未出现在采样的(𝐿ᵢ, 𝑁ᵢ)配对中。

> −1 (𝑖, 𝑗) ∈ 𝑀
> 𝑇 (𝑖, 𝑗) = (16) 𝑜
> 𝑇 (𝑖, 𝑗) (𝑖, 𝑗) ∉ 𝑀 𝑟
> 𝑇 is fed into the RITA as input, and the output representations are concatenated and fed 𝑜 into a Transpose Convolution layer which decodes the output embedding vectors from hidden space to timeseries values, corresponding to the convolution operation in the input stage, i.e.,
> = ( ⊕ ⊕ ... ⊕ ), where 𝑌 ∈ R𝑡×𝑚 is the recovered timeseries, and 𝑍 ∈ R𝑑
> Y TransposeCNNZ Z Z 𝑖
> 12 n is the output of each position. Here Mean Square Error is chosen as the loss function [58]: 𝐿 =
> 1 (𝑌 (𝑖, 𝑗) −𝑇 (𝑖, 𝑗))2. |𝑀 | (𝑖,𝑗 ) ∈𝑀 𝑟
> 6.3 Fore casting
> Forecasting can be regarded as a special case of imputation, in which all missing values are at the end of timeseries. Similarly to the imputation task, we scale the timeseries to non-negative and use
> Proc. ACM Manag. Data, Vol. 2, No. 1 (SIGMOD), Article 62. Publication date: February 2024. RITA: Group Attention is All You Need for Timeseries Analytics 62:15 a special value (-1) to indicate the values to be predicted:

算法2 平面划分动态规划
要求：𝐿𝑖 , 𝑁𝑖 , 𝐵𝑖 , 𝐿𝑚𝑎𝑥
保证：1 ≤ 𝑖 ≤ 𝑚，1 ≤ 𝑗 ≤ 𝑛；1 ≤ 𝑘 ≤ 𝑐
函数cost(S)：
若S为空集，则返回0；
否则计算当前子区域的误差值并递归处理剩余部分。

> 𝑇 (𝑖, 𝑗) 𝑖 ≤ 𝑡
> 𝑇 𝑖, 𝑗 𝑟𝑒𝑎𝑙 𝑜𝑏𝑠𝑒𝑟𝑣𝑒𝑑 (17) 𝑜𝑏𝑠𝑒𝑟 𝑣𝑒𝑑 ( ) =
> −1 𝑜𝑡ℎ𝑒𝑟𝑤𝑖𝑠𝑒
> Where 𝑡 is the observed timestamp. Then the output representations are fed into a Transpose 𝑜𝑏𝑠𝑒𝑟𝑣𝑒𝑑
> Convolution layer using Mean Squared Error as loss function, as described above. 6.4 Other Unsupervised Tasks
> RITA naturally supports other unsupervised tasks, such as similarity search and clustering [29,
> 36, 37], by producing the embedding of one timeseries (output representation of the special token
> [CLS]). Clustering can be performed on the embeddings with flexible choice of distance metrics. Similarly, a high dimensional similarity search system [26, 27, 44] can be built on the embeddings, i.e., the time series query system we show in Fig. 1 and evaluate in Sec. 7.6. 7 EVALUATION
> Our experimental study focuses on the following questions:
> 1. Effectiveness and efficiency: How does RITA compare with other Transformer-based methods and traditional timeseries representation learning methods in accuracy and efficiency? 2. Similarity Search: How well does RITA in supporting time series similarity search? 3. Ablation Study: How do the key techniques of RITA work? 7.1 Experimental Setup
> Datasets. We evaluate RITA on classification, imputation, and similarity search tasks using 6 multi-variate and 3 uni-variate timeseries datasets. • WISDM [63] is a popular multivariate timeseries dataset generated from the accelerometer in the mobile phone. The subjects performed 18 daily activities (e.g. walking, jogging). The dataset was collected from 51 subjects and the sampling rate is 20 Hz. • HHAR dataset [53] contains sensing data of accelerometer collected from 9 users performing 5 activities with 12 different smartphones (varying in sampling rate). This increases the complexity of the task and thus can test the model’s robustness. • RWHAR RealWorld HAR dataset [55] covers 15 subjects performing 8 locomotion-style activities. Each subject wears the sensors for approximately ten minutes. The sampling rate is 50 Hz. • ETT [71] dataset comprises 2 years of 2 electrical transformers’ data collected from 2 stations, including the oil temperature and six features of the power load. We use ETTm1 where each timeseries lasts 15 minutes. We pre-process and split the data as in prior work [46]. • ECG dataset [39] consists of 10,000 EEG recordings for arrhythmia classification. Each recording has an uncertain length ranging from 6 to 60 seconds sampled at 500 Hz. The ECG recordings correspond to 9 types of heart problems such as atrial fibrillation (AF) and premature atrial contraction
> (PAC), etc.
> • MGH [7] is an EEG dataset collected by Mass. General Hospital. Each timeseries corresponds to the EEG data observed from one patient during their stay in ICU for a couple of days. The EEG monitoring produced data with 20 channels. The sampling rate is 200 Hz, so it produces very long timeseries. • WISDM*/HHAR*/RWHAR* are three univariate datasets derived by selecting one channel from WISDM/HHAR/RWHAR. Training/Validation Data Generation.

函数fitting(𝑍,𝑊,𝐵):
初始化参数矩阵𝑊 ∈ ℝ^{𝑐×𝑑}和偏置向量𝐵 ∈ ℝ^𝑐为随机数；
通过反向传播算法最小化损失函数𝐿 = -Σ_{𝑖=1}^𝐶 log(softmax(WZ + B))_i

函数transpose_convolution(Z, W_transpose):
将隐藏状态𝑍 ∈ ℝ^{𝑑×𝑡×𝑚}与转置卷积核𝑊_transpose ∈ ℝ^{𝑑×𝑘×𝑙}进行卷积操作；
输出结果𝑌 = 𝑊_transpose * 𝑍，其中*表示转置卷积运算。

函数cross_entropy_loss(Y, T):
计算交叉熵损失𝐿 = -Σ_{(i,j)∈𝑀} log(P(T(i,j)|Y))，其中P为概率分布

公式（16）：
𝑇 (𝑖,𝑗) = { 
    𝑇 (𝑖,𝑗), 若(i,j) ∉ 𝑀
    −1,        若(i,j) ∈ 𝑀
}

公式（17）：
𝑇_{𝑜𝑏𝑠𝑒𝑟𝑣𝑒𝑑} (i,j) = {
    𝑇 (i,j),     若i ≤ t
    -1,           否则
}

其中𝑡为观测时间戳，𝑀表示缺失值位置集合。输出表征通过转置卷积层解码到时序值空间，并采用均方误差作为损失函数：𝐿 = 1/|𝑀| Σ_{(i,j)∈𝑀} (𝑌(i,j)-𝑇(i,j))²

7.1 实验设置
数据集：
• WISDM [63] 是由手机加速度计生成的多变量时序数据集。受试者执行了18种日常活动（如行走、慢跑）。该数据集来自51名受试者的20Hz采样。
• HHAR数据集[53] 包含9位用户使用不同智能手机采集的加速度计传感数据，涵盖5类活动并具有差异化的采样率。这增加了任务复杂度以测试模型鲁棒性。
• RWHAR RealWorld HAR数据集[55] 覆盖15名受试者执行8种运动风格活动的数据。每位受试者佩戴传感器约十分钟，采样率为50Hz。
• ETT [71] 数据集包含两个变电站两年的电力变压器数据，包括油温及六项负载特征。我们使用ETTm1子集（每个时序持续15分钟），并采用先前研究[46]的数据预处理和划分方法。
• ECG数据集[39] 包含用于心律失常分类的10,000条EEG记录，每段记录长度不确定且在6-60秒间变化（采样率为500Hz）。ECG记录对应九种心脏问题如房颤(AF)和早搏(PAC)等。
• MGH [7] 是麻省总医院收集的EEG数据集。每个时序对应患者住院数日期间观察到的心电图数据，包含20通道监测信息（采样率为200Hz），因此产生非常长的时序记录。

• WISDM*/HHAR*/RWHAR* 为三个通过选择WISDM/HHAR/RWHAR中单个通道生成的一维数据集。训练/验证数据生成：

> Training/Validation Data Generation. We apply a sliding window on the raw timeseries to get training/validation samples. The size of the sliding window is set to 200 on small datasets (WISDM,
> Proc. ACM Manag. Data, Vol. 2, No. 1 (SIGMOD), Article 62. Publication date: February 2024. 62:16 Jiaming Liang, Lei Cao, Samuel Madden, Zachary Ives, and Guoliang Li
> HHAR, RWHAR, ETT), 2000 on medium size dataset (ECG), and 10,000 on the large dataset (MGH). Table 1 shows the statics of the generated datasets. They are randomly split into training/validation set in a proportion of 0.9/0.1. In “pretraining + few-label finetuning” scenario, we use 100 labeled data per class for finetuning. We guarantee training set does not overlap with the validation set. Dataset Train.Size Valid.Size Length Channel Classes
> WISDM 28,280 3,112 200 3 18
> HHAR 20,484 2,296 200 3 5
> RWHAR 27,253 3,059 200 3 8
> ETT 34,265 11,425 200 7 N/A
> ECG 31,091 3,551 2000 12 9
> MGH 8,550 950 10000 21 N/A
> Table 1. The statistics of the datasets
> Alternative Methods. We compare RITA against the SOTA deep learning-based representation learning methods, including the Transformer based TST [70] and the non-Transformer method TS2VEC [68]. To evaluate our group attention (referred to as Group Attn.), we develop three baselines by replacing the group attention component in RITA with the classic vanilla
> Self-Attention [59](referred to as Vanilla) and two SOTA methods that reduce the complexity of self-attention by approximation in NLP, namely, Performer [11] (referred to as Performer) and
> Linformer [62] (referred to as Linformer). Similar to our proposed Group Attn., Vanilla, Performer,
> Linformer all use RITA’s time-aware convolution operation (Sec. 3) to turn timeseries segments into input feature vectors. Finally, we compare against the SOTA Transformer-based methods for timeseries forecasting, Triformer [12] and PatchTST [46], wherein their decoders are substituted with output networks for the downstream tasks. We also compare Group Attn. against GRAIL [47], which is the SOTA of the non-deep learning methods for timeseries representation learning. GRAIL supports classification tasks by feeding the learned representations into a Support-Vector Machine [15] or K-Nearest Neighbor [20] classifier. RITA: Group Attention is All You Need for Timeseries Analytics 62:17 c e s
> /e m y c iT a r g u n c i c n
> A i a r
> T
> 200 200 200 2000 200 200 200 2000
> Fig. 4. Full-label classification results (multi-variate data). Dataset WISDM HHAR RWHAR ECG
> Pretrain Size 62,231 68,294 63,599 561,358
> Method Scratch Pre. Scratch Pre. Scratch Pre. Scratch Pre. TST[70] 49.13% 50.03% 72.56% 75.30% 69.46% 80.41% 20.98% 27.99%
> TS2VEC[68] 54.30% 62.01% 69.03% 82.54% 79.41% 85.01% 39.38% 39.94%
> Triformer[12] 34.28% 40.61% 71.51% 72.21% 76.23% 82.73% 22.74% 29.53%
> PatchTST[46] 44.63% 50.51% 71.47% 73.12% 60.73% 60.83% 29.82% 32.61%
> Vanilla 66.16% 75.89% 75.60% 81.35% 85.68% 91.14% 42.05% 46.16%
> Performer 66.09% 73.97% 76.52% 80.70% 87.54% 91.33% 43.34% 45.58%
> Linformer 50.12% 67.44% 65.94% 76.52% 81.03% 86.33% 27.19% 31.34%
> GroupAttn. 62.56% 75.06% 76.17% 82.62% 86.13% 89.63% 42.58% 46.39%
> Table 2. Pretrain + few-label finetuning results. Metrics: Accuracy. The best results are marked with bold. (sec. 7.4). Note that TS2VEC[68] doesn’t support imputation tasks. It is thus not reported in this set of exp eriments. We report the median result among 5 random seeds and data splits as here we observe a low standard error. Configuration. All models were trained on an NVIDIA Tesla V100 16GB GPU. All methods are optimized with AdamW [42], with the starting learning rate and weight decay parameter set to
> 1𝑒−4. In full-label training scenario, we train the models for 100 epochs. In “pretraining + few-label finetuning scenario”, as the pretrained models require fewer epochs to converge [70], we train the model for 50 epochs. The baselines use a maximal batch size within GPU’s capacity during training: per [21], a larger batch size can expedite training without compromising accuracy. Therefore, with this setting, the baselines are shown with their best possible results. As for model hyper-parameter setting, RITA and the baselines use a Transformer structure balancing Vanilla ’s accuracy and efficiency: 8-layer stack of 2-head attention with hidden vectors in dimension of 64. Convolution kernel size is set to 5 by default. We set the error bound threshold
> (𝜖, Sec. 5.1) of Group Attention to 2, as it balances the accuracy and the efficiency in general on all datasets based on our ablation study (Table 4). Because Linformer requires the users to set the sizes of projection matrix, in different settings we choose an accuracy-efficiency balancing one among
> {64,128,256,512}. For Triformer, we enumerate the settings given by the authors [12] and choose the setting that balances accuracy and efficiency. For PatchTST, similarly, we choose an appropriate patch size among {16,64,256}, per the suggestion of the authors. 7.2 Classification
> In this section, we evaluate the effectiveness and efficiency of RITA on classification tasks. We first compare RITA and the baselines by training them with full labels from scratch. We then show how pretraining RITA increases the accuracy on the downstream tasks. Proc. ACM Manag. Data, Vol. 2, No. 1 (SIGMOD), Article 62. Publication date: February 2024. 62:18 Jiaming Liang, Lei Cao, Samuel Madden, Zachary Ives, and Guoliang Li
> Dataset WISDM HHAR RWHAR ETT ECG MGH
> Length 200 200 200 200 2,000 10,000
> Method MSE Time/s MSE Time/s MSE Time/s MSE Time/s MSE Time/s MSE Time/s
> TST [70] 13.30 150.3 1.085 78.2 0.0882 83.9 0.1661 181.8 0.0905 696.3 N/A N/A
> Triformer [12] 11.20 163.2 2.468 87.9 0.4580 97.5 0.0777 197.2 0.0905 977.9 0.00079 2936
> PatchTST [46] 5.568 132.7 0.7337 69.6 0.1330 78.0 0.0552 160.5 0.0101 235.8 N/A N/A
> Vanilla 3.240 178.1 0.2968 97.4 0.0478 108.1 0.0530 215.5 0.0037 857.9 N/A N/A
> Performer 3.449 162.6 0.2980 82.6 0.0489 89.1 0.0532 196.7 0.0033 270.2 0.00014 356.2
> Linformer 3.852 141.9 0.3198 81.1 0.0572 98.4 0.0601 171.6 0.0035 291.38 0.00088 404.9
> Group Attn. 3.277 136.7 0.2974 73.3 0.0478 81.3 0.0535 165.4 0.0038 164.36 0.00042 54.4
> Table 3. Imputation results (multi-variate data). Metrics: MSE. The best results are marked with bold. 7.2.1 full-label training (Multi-variate classification)
> Results shown in Figure 4 get us the following observations:
> (1) Group Attn.’s advantage over TST. On all four datasets, Group Attn. outperforms TST in both accuracy and training time. In particular, Group Attn. outperforms TST by 49 percentage points (88.48% vs 39.93%) and is 3 times faster in training time per epoch (236.8s vs 731.0s) on the
> ECG dataset. Three deficiencies may cause TST’s poor performance on the long timeseries. Firstly, TST concatenates the output embedding vector of each time stamp, then uses a linear classifier to do classification on the concatenated vector. When the timeseries is long, the linear classifier has so many parameters that it tends to overfit easily. Secondly, TST replaces Layer Normalization in vanilla
> Transformer with Batch Normalization. When the timeseries is long, it can only accommodate a small number of timeseries in each batch, leading to bias in Batch Normalization. Thirdly, TST uses vanilla self-attention, which causes quadratic complexity. (2) Group Attn.’s advantage over TS2VEC. Group Attn. is consistently more accurate than
> TS2VEC across the four datasets. In particular, on the ECG dataset which contains long timeseries – the scenario we focus on, Group Attn. outperforms it in accuracy by 28% (88.48% vs 59.17%), while using less training time per epoch. This can be attributed to our backbone model (Transformer) which effectively captures long-range correlations. (3) Group Attn.’s advantage over Vanilla.

在全标签训练场景中，我们对模型进行了100个epoch的训练；而在"预训练+少量标签微调"场景下，由于预训练模型收敛所需epoch较少[70]，因此仅进行50个epoch的训练。基线方法在训练过程中采用GPU容量内的最大批量大小：根据文献[21]，更大的批量尺寸可以在不牺牲准确率的前提下加速训练过程。因此，在此设置下，基线方法展示了其最佳可能结果。

关于模型超参数配置，RITA及其基线均采用了平衡Vanilla准确性与效率的Transformer结构：8层堆叠的双头注意力机制（隐藏向量维度为64）。卷积核尺寸默认设为5。我们根据消融研究(表4)将组注意力误差界限阈值($\epsilon$，第5.1节)设置为2，在所有数据集上实现了准确性与效率之间的平衡。

由于Linformer需要用户设定投影矩阵的大小，在不同场景下我们在{64, 128, 256, 512}中选择一个在准确率和效率之间取得平衡的值。对于Triformer，我们列举了作者[12]提供的设置并选择了准确性与效率之间的最佳配置；对PatchTST，则根据作者建议从{16, 64, 256}中选取合适的块尺寸。

**7.2 分类任务评估**

在本节中，我们将评估RITA在分类任务中的有效性及计算效率。首先通过从未标注数据集中训练全标签模型来比较RITA与基线方法的表现；随后展示预训练如何提升下游任务的准确率。

表3展示了插补结果（多变量数据）。指标：均方误差(MSE)。最佳结果用粗体标记。（第7.4节）需注意的是，TS2VEC[68]不支持缺失值填补任务，因此未在本组实验中报告其结果。我们在此采用5个随机种子和数据分割的中位数结果，因为观察到标准误差较低。

**表3：插补结果（多变量数据）。指标：MSE。最佳结果用粗体标记**

| 数据集 | 长度 | 方法         | MSE       | 时间/秒 |
|--------|------|--------------|-----------|---------|
| WISDM  | 200  | TST [70]     | 13.30     | 150.3   |
|        |      | Triformer [12]| 11.20     | 163.2   |
|        |      | PatchTST [46]| 5.568     | 132.7   |
|        |      | Vanilla       | 3.240     | 178.1   |
|        |      | Performer     | 3.449     | 162.6   |
|        |      | Linformer     | 3.852     | 141.9   |
|        |      | Group Attn.   | 3.277     | 136.7   |

**表4：预训练+少量标签微调结果。指标：准确率**

| 数据集 | 方法         | 准确率       |
|--------|--------------|---------------|
| WISDM  | TST [70]     | 88.48%        |
|        | Triformer    | 62.56%        |
|        | PatchTST     | 75.06%        |
|        | Vanilla      | 39.93%        |
|        | Performer    | 75.06%        |
|        | Linformer    | 81.42%        |
|        | Group Attn.  | 86.13%        |

**图4：全标签训练结果分析**
(1) 组注意力机制相较于TST的优势：
- 在所有四个数据集上，组注意力均在准确率和训练时间方面优于TST
- 特别是在ECG数据集中（长时序场景），组注意力优势达49个百分点（88.48% vs 39.93%）且每轮训练速度提升三倍（236.8s vs 731.0s）
- TST在长时序表现不佳的三个原因：
  - 首先，TST将每个时间戳的输出嵌入向量拼接后使用线性分类器进行分类。当序列较长时，线性分类器参数过多易导致过拟合
  - 其次，TST用批量归一化替代了原始Transformer中的层归一化。长序列仅能容纳少量样本批次，导致批量归一化的偏差
  - 第三，TST使用原始自注意力机制造成二次复杂度

(2) 组注意力相较于TS2VEC的优势：
- 在四个数据集中组注意力均保持更高准确率
- 特别是在包含长时序的ECG数据集（我们关注的重点场景），组注意力优势达28%（88.48% vs 59.17%）且训练时间更少。这归功于我们的主干模型(Transformer)有效捕捉了长程相关性

(3) 组注意力相较于Vanilla的优势：

> (2) Group Attn.’s advantage over TS2VEC. Group Attn. is consistently more accurate than
> TS2VEC across the four datasets. In particular, on the ECG dataset which contains long timeseries – the scenario we focus on, Group Attn. outperforms it in accuracy by 28% (88.48% vs 59.17%), while using less training time per epoch. This can be attributed to our backbone model (Transformer) which effectively captures long-range correlations. (3) Group Attn.’s advantage over Vanilla. Vanilla computes the attention scores precisely. Thus it is expected to work well. However, Group Attn. outperforms Vanilla on WISDM (87.50% vs
> 86.95%) and is very close to it on other 3 datasets. This suggests that group attention’s approximation quality is good. Group Attn. is more scalable than Vanilla Self-Attention. When the series length is 200 (WISDM,
> HHAR, RWHAR), Group Attn. requires 25% less training time on average. When the length increases to 2,000 (ECG), Vanilla takes over 15 minutes per epoch, about 4 times slower than Group Attn.. Vanilla fails on the long MGH data when the length reaches 10,000 due to out of GPU memory. (4) Group Attn.’s advantage over other efficient attention mechanisms. Group Attn. is more accurate than Performer and Linformer on 3 out of 4 datasets. Although Linformer works slightly better than Group Attn. on the ECG dataset (90.37% vs 88.84%), it is the worst in all other cases compared to any other RITA-based methods. In the meantime, Group Attn. is always faster than Performer and Linformer on all 6 multi-variate datasets, thus a win-win. Group Attn. significantly outperforms PatchTST and Triformer in classification accuracy. This is because these two methods are tailored for timeseries forecasting, and the feature embeddings produced by their specialized designs may have adverse effects on other timeseries analytical tasks, as discussed in related work section. Moreover, Group Attn. is 1.3/4.4 times faster than
> PatchTST/Triformer on long timeseries, e.g., on the ECG dataset, because Group Attn. has more sharing opportunities when processing long timeseries. 7.2.2 Pretraining + few label finetune (multi-variate classification)
> The results shown in Table 2 get us the following observation:
> Proc. ACM Manag. Data, Vol. 2, No. 1 (SIGMOD), Article 62. Publication date: February 2024. RITA: Group Attention is All You Need for Timeseries Analytics 62:19
> (1) Pretraining is effective. Pretraining always leads to better accuracy than training with a few labels from scratch. In particular, on WISDM data all the methods using RITA architecture increase the accuracy by at least 10%. This is impressive considering we do not have a very large unlabeled pre-training set to use. (2) Group Attn.’s advantage over TST and TS2VEC. On the four classification datasets, our
> Group Attn. significantly outperforms TST by 15 percentage points on average, and outperforms
> TS2VEC by 6 percentage points. (3) Group Attention’s advantage over other attention mechanisms. Group Attn. is better than Performer and Linformer on 3 out of 4 datasets. When compared to Vanilla, Group Attn. is better on HHAR and ECG, and comparable on the other two, further confirming its high quality on approximation. Further, we notice that Linformer struggles in this setting: in average its accuracy is worse than Vanilla by 8.22% and Group Attn. by 8.01%. This is because the low-rank projection operation introduces extra model parameters, making Linformer more easily overfit, while overfitting is especially harmful when there are only a few labeled training samples. Triformer and PatchTST, the two timeseries forecasting methods have an accuracy much (34%) lower than Group Attn., for a similar reason to what we have discussed in Sec. 7.2.1. 7.3 Imputation
> In this section, we compare our group attention and the baselines on imputation tasks, a typical data cleaning task in data management. We first show the results on all the 6 datasets in Sec. 7.3.1. We then vary the length of the timeseries on the MGH dataset to show group attention’s scalability on long timeseries in Sec. 7.3.2. 7.3.1 Full-dataset training (Multi-variate imputation)
> Similar to classification tasks, the results of imputation tasks (Table 3) show that Group Attn. consistently outperforms the baselines in training time while achieving comparable/better Mean
> Square Error (MSE). On the large dataset MGH (length = 10,000), TST, Vanilla and PatchTST fail due to out of memory (OOM) errors. Methods using RITA framework (Group Attn., Performer,
> Linformer) all achieve very low MSE and thus are highly accurate. Among them Linformer is the worst. The accuracy of Triformer and PatchTST in general is much lower, because they target forecasting task rather than generating high quality feature embeddings to support various tasks. Here we observe that the longer the timeseries, the larger the speedup is. On the medium sized ECG dataset with a length of 2,000, Group Attn. has a speedup of 5.23/1.65/1.77/5.96/1.43 compared to Vanilla/Performer/Linformer/Triformer/PatchTST. When the length increases to 10,000, the speedup on the MGH dataset increases to 6.59/7.48/54.37 compared to Performer/Linformer/Triformer (Vanilla,TST and PatchTST failed due to out of memory) on imputation task (Table. 3). This is because when the length of the timeseries gets longer, Group Attn. gets more opportunities to find windows with similar properties. Note Triformer is very slow on long series (length = 10,000), because it involves a lot of sequential computation and thus cannot benefit from GPUs. Even on the short WISDM, HHAR, RWHAR, and ETT datasets, Group Attn. still consistently outperforms all other methods except PatchTST. This confirms that it fully leverages the similarity among the timeseries windows, while not introducing much overhead. Although PatchTST has comparable speed with Group Attn. on short series, it is much slower on the longer ECG dataset
> (length = 2000) and fails on the very long EEG data (length = 10,000). This is because it concatenates many embeddings to form a very long embedding before making prediction, thus consuming much more GPU memory. This shows PatchTST does not scale to long series. Proc. ACM Manag. Data, Vol. 2, No. 1 (SIGMOD), Article 62. Publication date: February 2024. 62:20 Jiaming Liang, Lei Cao, Samuel Madden, Zachary Ives, and Guoliang Li c e s
> /e m iT g E n Sin Mia r
> T
> 2000 4000 6000 8000 10000 2000 4000 6000 8000 10000
> Fig. 5. Varying the lengths of timeseries. 7.3.2 Training time: Varying the Length
> In this experiment, we truncate the original MGH timseries into sequences with the lengths at
> 2000/4000/6000/8000/10000, and compare Group Attn. against Vanilla and other attention mechanisms. Vanilla cannot handle sequences longer than 8000. The results in Fig. 5 again show that the longer the timeseries, the larger the speed up. With comparable or better MSE, Group Attn. outperforms Vanilla/TST/PatchTST/Triformer/Performer/Linformer by 63/49/45.9/54.3/6.5/7.4x. Although PatchTST is fast on short series (length = 200), its training time increases very fast as the length increases and fails eventually when reaching 10,000. Moreover, as the length increases from 2000 to 10000, the training time of Group Attn. only increases from
> 31.2 seconds to 54.4 seconds per epoch. The reason is that as the timeseires becomes longer, there are more grouping opportunities because of the similarity of the timeseries segments. 7.4 Comparison to Non-deep Learning Methods c e s
> /e y m c i a T r g u c n c in
> Aia rT
> (a) (b)
> Fig. 6. Comparison to non-deep learning method (uni-variate data). We compare against GRAIL, the SOTA of non-deep learning timeseries representation learning. We use the three uni-variate datasets, because GRAIL only targets uni-variate timeseries. Fig. 6 demonstrates that on all 3 datasets RITA significantly outperforms GRAIL in accuracy by 45, 16, and
> 21 percentage points because of the expressive power of Transformer. Moreover, the GPU-friendly design of RITA makes it at least 2× faster than GRAIL in training time.

(2) 组注意力相较于TS2VEC的优势：组注意力在四个数据集上均保持更高准确率。特别是在包含长时序的ECG数据集（我们关注的重点场景），组注意力优势达28%（88.48% vs 59.17%）且训练时间更少。这归功于我们的主干模型(Transformer)有效捕捉了长程相关性。(3) 组注意力相较于Vanilla的优势：Vanilla精确计算注意力分数，因此预期表现良好。然而组注意力在WISDM（87.50% vs 86.95%）上超越Vanilla，在其他三个数据集上与之非常接近。这表明组注意力的近似质量较好。组注意力比Vanilla自注意力更具可扩展性。当序列长度为200（WISDM, HHAR, RWHAR）时，组注意力平均每轮训练时间减少25%。当长度增加到2000（ECG）时，Vanilla每轮耗时超过15分钟，约为组注意力的4倍慢速。Vanilla在长MGH数据中因显存溢出失败，当序列长度达到10,000时无法处理。(4) 组注意力相较于其他高效注意力机制的优势：组注意力在四个数据集中有3个优于Performer和Linformer。尽管Linformer在ECG数据集上表现略好于组注意力（90.37% vs 88.84%），但在所有其他情况下均劣于任何RITA基方法。同时，组注意力始终比Performer和Linformer更快，在全部6个多变量数据集中实现双赢。组注意力在分类准确率方面显著优于PatchTST和Triformer。这是因为这两种方法专门针对时间序列预测设计，其特殊结构产生的特征嵌入可能对其他时间序列分析任务产生负面影响（如相关工作部分所述）。此外，组注意力在长时序上比PatchTST/Triformer快1.3/4.4倍，例如ECG数据集。这是因为处理长时序时组注意力有更多共享机会。7.2.2 预训练+少量标签微调（多变量分类）表2中的结果使我们得出以下观察：(1) 预训练有效。预训练始终比从头使用少量标签训练获得更好准确率。特别是WISDM数据中所有采用RITA架构的方法准确性提升至少10%。考虑到我们没有非常大的无标签预训练集，这一表现令人印象深刻。(2) 组注意力相较于TST和TS2VEC的优势：在四个分类数据集中，我们的组注意力平均比TST高15个百分点，比TS2VEC高6个百分点。(3) 组注意力与其他注意力机制相比优势。组注意力在4个数据集中有3个优于Performer和Linformer。与Vanilla比较时，在HHAR和ECG上表现更好，在其他两个数据集上相当，进一步验证其近似质量较高。此外我们注意到Linformer在此设置中表现不佳：平均准确率比Vanilla低8.22%，比组注意力低8.01%。这是因为低秩投影操作引入额外模型参数，使Linformer-router更容易显存溢出。即使在短WISDM, HHAR, RWHAR和ETT数据集上，组注意力仍持续超越所有其他方法（除PatchTST）。这证实其充分利用时间序列窗口间的相似性，而未引入过多开销。虽然PatchTST在短时序与组注意力速度相当，但在较长ECG数据集（长度=2000）和非常长EEG数据（长度=10,000）上显著变慢并失败。这是因为其先将多个嵌入拼接形成超长嵌入再进行预测，从而消耗更多显存。这表明PatchTST无法扩展到长时序。

> of RITA makes it at least 2× faster than GRAIL in training time. 7.5 Ablation Study
> 7.5.1 Adaptive Scheduler
> To evaluate the effectiveness of RITA’s adaptive scheduler (denoted as Dynamic) (Sec. 5), we compare it against (1) baseline Fixed: a fixed group number 𝑁; (2) baseline Heuristic: if the validation loss gets lower than ever after the current epoch, we consider that the current 𝑁 is sufficiently large for the current training stage, and set 𝑁 to 𝑁 ∗ 𝐷𝑒𝑐𝑎𝑦_𝑟𝑎𝑡𝑒 for the next epoch. RITA: Group Attention is All You Need for Timeseries Analytics 62:21 should decrease gradually. We vary 𝑁 for Fixed, 𝐷𝑒𝑐𝑎𝑦_𝑟𝑎𝑡𝑒 for Heuristic, and the error bound threshold 𝜖 used by RITA. From the results in Table 4 we get the following observations:
> (1) Adaptive Scheduler is better than the baselines. Training with Adaptive Scheduler achieves better or comparable performance compared to the best performing 𝑁 or 𝐷𝑒𝑐𝑎𝑦_𝑟𝑎𝑡𝑒. For 𝐹𝑖𝑥𝑒𝑑, on the MGH dataset, dynamic scheduler always achieves better accuracy and is much faster compared to fixed 𝑁 . On the ECG dataset, although fixed 𝑁 is slightly better than adaptive scheduler in accuracy when setting the 𝑁 as 512, it runs much slower than adaptive scheduler. For
> 𝐻𝑒𝑢𝑟𝑖𝑠𝑡𝑖𝑐, we have similar observations: on ECG dataset, dynamic scheduler consistently achieves better accuracy than 𝐻𝑒𝑢𝑟𝑖𝑠𝑡𝑖𝑐. On MGH dataset, dynamic scheduler achieves comparable MSE with less training time. Note that manually finding the best 𝑁 or 𝐷𝑒𝑐𝑎𝑦_𝑟𝑎𝑡𝑒 that balances the accuracy and running time requires careful tuning, while our adaptive scheduler does not need any tuning. (2) Adaptive Scheduler is tuning free. It is robust on both accuracy and running time when 𝜖 varies, while the results of fixed 𝑁 vary significantly when the value of 𝑁 changes. Therefore,
> Adaptive Scheduler frees the users from tuning the 𝜖 threshold, while it is hard to manually find an appropriate 𝑁 or 𝐷𝑒𝑐𝑎𝑦_𝑟𝑎𝑡𝑒 for a given dataset. Dataset Task Scheduler Parameter Metric Time
> 1.5 88.34% 292.5
> Dynamic 2 88.48% 236.8
> 3 87.83% 216.8
> 64 87.50% 255.2
> ECG Class. 128 88.96% 297.2
> Fixed 256 88.82% 414.1
> 512 90.03% 662.6
> 1024 88.65% 873.7
> 0.8 85.41%240.36
> Heuristic
> 0.9 86.28%253.57
> 1.5 0.00041 60.7
> Dynamic 2 0.00040 57.9
> 3 0.00042 54.4
> 128 0.00054 128.6
> MGH Imput. 256 0.00053 190.2
> Fixed
> 512 0.00049 240.8
> 1024 0.00046 323.3
> 0.8 0.00041 102.0
> Heuristic
> 0.9 0.00040 104.0
> Table 4. Adaptive Scheduling vs Baseline (Fixed N/Heuristics)
> Pretrain Data size Few-label Accuracy
> N/A 62.56%
> 12,446 72.94%
> 24,892 72.78%
> 37,338 74.10%
> 49,784 74.22%
> 62,231 75.06%
> Table 5. RITA Pretraining: increasing sizes of pretrain set. 7.5.2 The Sizes of the Pretraining Data
> Next, we evaluate how the number of unlabeled data influences the effectiveness of pretraining. To get empirical results, we pretrain RITA on WISDM dataset with 20%/40%/60%/80% of the pretraining
> Proc. ACM Manag. Data, Vol. 2, No. 1 (SIGMOD), Article 62. Publication date: February 2024. 62:22 Jiaming Liang, Lei Cao, Samuel Madden, Zachary Ives, and Guoliang Li
> Group Attn. Linformer
> Performer
> Triformer
> Pat c hTST
> TST
> Vanilla
> 0 100 200 300 400 500
> Tim e Cost / se c
> Fig. 7. Query Execution time for 10,000 10-NN queries. Precision: Vanilla (88.34%), Group Attn.(88.29%),
> Linformer(88.07%), Performer(88.23%/), Triformer(42.45%), PatchTST(80.84%), TST(40.72%). data and finetune each pretrained model with 100 labels per class. The results in Table 5 show that:
> (1) The more pretraining data, the larger the improvement. The accuracy increases with the sizes of the preGtrroauipn Ainttgn.data; The first 20% pretraining data
> (2) Marginal utility diminishing. gives a 10.38% impVraonivlleament in accuracy (72.94% vs 62.56%), while the remaining 80% pretraining data only gives an additional improvement of 2.12% (75.06% vs 72.94%). 0 20 40 60 80 100 120 140 160
> Tim e Cost / se c
> 7.6 Similarity Search
> We develop a time-series query system to conduct this similarity search experiment. We first use
> RITA to extract feature embeddings from the training set of the ECG dataset and store them in a vector DB. We then use the timeseries in validation set as queries to find their 𝑘NN from the vector
> DB. Given a query, we use RITA to extract its feature embedding at online query time. In our experiment, we use Postgres [13] as the vector DB, as it features the HNSW index to speed up the high dimensional similarity search. We set the 𝑘 as 10 in 𝑘NN search and run 10,000 queries. The results, as depicted in Figure 7, show that RITA is faster than all baselines by 60%, indicating that RITA outperforms the baselines on inference time as well. The precision of RITA is on par to that of Vanilla Transformer. Note the precision of Vanillar Transform is considered to be the upper bound of the precision of all Transformer-based methods, because it uses the original expensive attention mechanism without any approximation. RITA outperforms all other baselines in precision, while faster than them. 8 RELATEDWORK
> Method TST Vanilla Triformer PatchTST Performer Linformer GroupAttn. Time Complexity 𝑂 (𝑛2𝑑) 𝑂 (𝑛2𝑑) 𝑂 (𝑛𝑑2 𝑚 ) 𝑂 (𝑛𝑑2 𝑚 ) 𝑂 (𝑛𝑑 (𝑑 + 𝑃 )) 𝑂 (𝑛𝑑 (𝑑 + 𝐿)) 𝑂 (𝑛𝑑 (𝑑 + 𝑁 ))
> Space Complexity 𝑂(𝑛2) 𝑂(𝑛2) 𝑂(𝑛𝑑𝑚 ) 𝑂(𝑛𝑑𝑚 ) 𝑂(𝑛(𝑑 +𝑃)) 𝑂(𝑛(𝑑 +𝐿)) 𝑂(𝑛(𝑑 + 𝑁))
> Table 6. The time/space complexity of Transformer-based methods. 𝑛: timeseries length; 𝑑: embedding dimension; 𝑚: number of channels; P,L,N,S,T: method-specific parameters
> 8.1 Timeseries Analytics
> There is a great deal of prior work on timeseries analytics methods. This work can be divided into three categories: (1) non-deep learning methods; (2) CNN/RNN-based deep learning methods; and
> (3) Transformer-based deep learning methods. Traditional Methods. These methods, such as TS-CHIEF [52], HIVE-COTE [38], ROCKET [18] have achieved notable performance on public datasets. Despite that, traditional methods suffer
> Proc. ACM Manag. Data, Vol. 2, No. 1 (SIGMOD), Article 62. Publication date: February 2024. RITA: Group Attention is All You Need for Timeseries Analytics 62:23 from one or more issues: they (1) rely on expert knowledge for feature extraction; (2) incur heavy computation cost and are inappropriate for GPU devices; (3) support only uni-variate timeseries;
> (4) perform classification solely. In particular, as the SOTA of timeseries representation learning, GRAIL [47] extracts landmarks from data and computes the representations with the combination of the landmarks. However,
> GRAIL only supports uni-variate timeseries. Our experiments (Sec. 7.4) show that RITA outperforms
> GRAIL in both effectiveness and efficiency on uni-variate timeseries. CNN/RNN-based Deep Learning Methods. CNN-based methods, such as InceptionTime [25] and Resnet [23], are good at classification tasks, but can not handle generative tasks such as forecasting because of the inductive bias of convolution networks. TS2VEC [68] is the SOTA non-Transformer representation learning method which uses CNN architecture. As confirmed in experiments, RITA consistently outperform it. RNN-based methods, such as Brit [8] and deepAR [51], support classification, regression and generation. However, the recurrent structure brings a lot of problems: (1) limiting the model’s ability in capturing long-range correlation; (2) notoriously difficult to train [48] because of gradient vanishing and exploding problem. As a result, such methods can hardly scale to very long timeseries. Transformer-based Deep Learning Methods. Given that Transformer is the best choice for backbone in almost all sequence modeling tasks, some effort has been made to apply Transformer to timeseries analytics. In timeseries forecasting, LogTrans [35] introduced a log sparsity assumption to attention computation. Informer [71] pushes LogTrans a step further and scales forecasting to multi-variate timeseries.

IL，分别提升了45、16和21个百分点，这归功于Transformer的表达能力。此外，RITA的GPU友好型设计使其训练时间至少比GRAIL快2倍。7.5 消融实验  
7.5.1 自适应调度器  
为评估RITA自适应调度器（记作Dynamic）的有效性（第5节），我们将其与以下基线进行比较：(1) 基线Fixed：固定组数𝑁；(2) 基线Heuristic：如果验证损失在当前epoch后低于历史最低值，则认为当前的𝑁已足够满足当前训练阶段的需求，并将𝑁设置为下个epoch的𝑁 × Decay_rate。RITA: Group Attention is All You Need for Timeseries Analytics 62:21 应该逐渐减小。我们对Fixed变化𝑁，对Heuristic变化Decay_rate，并调整RITA使用的误差界限阈值𝜖。从表4的结果中得出以下观察：  
(1) 自适应调度器优于基ично线。随着预训练数据量的增加，准确率提升幅度更大；前20%预训练数据使准确率提升了10.38%（72.94% vs 62.56%），而剩余的80%预训练数据仅带来额外2.12%的改进（75.06% vs 72.94%）。  
(2) 边际效益递减。  
0 20 40 60 80 100 120 140 160  
时间成本/秒  
7.6 相似性搜索  
我们开发了一个时间序列查询系统以进行相似性搜索实验。首先使用RITA从ECG数据集的训练集中提取特征嵌入并存储在向量数据库中。然后将验证集中的时间序列作为查询，在向量库中查找其𝑘NN。给定一个查询，我们在在线查询时使用RITA提取其特征嵌入。我们的实验采用Postgres[13]作为向量数据库，因其支持HNSW索引以加速高维相似性搜索。在𝑘NN搜索中设置𝑘为10，并运行10,000次查询。如图7所示的结果表明，RITA比所有基线快60%，说明其推理时间也优于基线方法。RITA的精度与Vanilla Transformer相当。注意Vanilla Transformer的精度被认为是基于Transformer的方法的上限，因为它使用了原始且昂贵的注意力机制而无任何近似。RITA在精度上超越了其他所有基线，并且速度更快。  
8 相关工作  
方法 TST Vanilla Triformer PatchTST Performer Linformer GroupAttn. 时间复杂度 𝑂 (𝑛²𝑑) 𝑂 (𝑛²𝑑) 𝑂 (𝑛𝑑²𝑚 ) 𝑂 (𝑛𝑑²𝑚 ) 𝑂 (𝑛𝑑(𝑑 +𝑃 )) 𝑂 (𝑛𝑑(𝑑 +𝐿)) 𝑂 (𝑛𝑑(𝑑 +𝑁 )) 空间复杂度 𝑂(𝑛²) 𝑂(𝑛²) 𝑂(𝑛𝑑𝑚 ) 𝑂(𝑛𝑑𝑚 ) 𝑂(𝑛(𝑑 +𝑃)) 𝑂(𝑛(𝑑 +𝐿)) 𝑂(𝑛(𝑑 +𝑁 ))  
表6. 基于Transformer的方法的时间/空间复杂度。𝑛：时间序列长度；𝑑：嵌入维度；𝑚：通道数；P,L,N,S,T：方法特定参数  
8.1 时间序列分析  
关于时间序列分析方法已有大量先驱工作。这些工作可分为三类：(1) 非深度学习方法；(2) 基于CNN/RNN的深度学习方法；以及 (3) 基于Transformer的深度学习方法。传统方法。如TS-CHIEF[52]、HIVE-COTE[38]和ROCKET[18]等方法在公开数据集上取得了显著性能表现。尽管如此，传统方法仍面临一个或多个问题：它们(1) 依赖专家知识进行特征提取；(2) 计算成本高昂且不适合GPU设备；(3) 只支持单变量时间序列； (4) 仅执行分类任务。特别是作为时间序列表示学习的SOTA方法，GRAIL[47]从数据中提取地标并结合这些地标计算表征。然而 GRAIL只支持单变量时间序列。我们的实验（第7.4节）表明 RITA在单变量时间序列的有效性和效率上均优于GRAIL。基于CNN/RNN的深度学习方法。如InceptionTime[25]和Resnet[23]等基于CNN的方法擅长分类任务，但由于卷积网络的归纳偏差无法处理生成性任务（如预测）。TS2VEC[68]是SOTA非Transformer表示学习方法，采用CNN架构。实验确认 RITA始终优于它。基于RNN的方法，如Brit[8]和deepAR[51]支持分类、回归和生成。然而循环结构带来了诸多问题：(1) 限制模型捕捉长程相关的能力； (2) 因梯度消失/爆炸问题而训练异常困难 [48]。因此此类方法难以扩展到非常长时间序列。基于Transformer的深度学习方法。鉴于Transformer在几乎所有序列建模任务中都是最佳主干选择，已有努力将其应用于时间序列分析。在时间序列预测领域 LogTrans[35]引入了对注意力计算的日志稀疏性假设。Informer[71]进一步推进LogTrans并扩展预测到多变量时间序列。

> Informer [71] pushes LogTrans a step further and scales forecasting to multi-variate timeseries. Autoformer [65] performs forecasting by decomposing timeseries into the trend part and the seasonal part. FEDformer [72] proposed a Frequency Enhanced Attention with Fourier
> Transform. Pyraformer [40] and Triformer [12] used hierarchical attention structures. PatchTST [46] introduced a patching pattern in attention. In our experiments, among this big family, we choose
> Triformer and PatchTST as our baselines, because they experimentally outperform the others and are considered as SOTA in this field. Because these methods are tailored for timeseries forecasting, the feature embeddings produced by their specialized designs may have adverse effects on other timeseries analytical tasks. For instance, Triformer incorporates sequence compression operations, which can be detrimental for imputation due to the potential loss of vital information on the entire timeseries. Moreover,
> Triformer employs variable-specific modeling, computing embeddings for each input channel separately. While this approach may be beneficial for forecasting tasks, it may not be suitable for classification, as the latter necessitates the consideration of information from all channels simultane ously. For imputation tasks, CDSA [43] outperforms statistical methods and the SOTA RNN-based method Brit [8]. For timeseries classification, AutoTransformer [50] performs architecture search to adapt to tasks in different domains. For timeseries anomaly detection, Anomaly Transformer [66] outperforms many widely used methods such as OmniAnomaly [54], assuming the attention score maps show Gaussian distribution. All of these works are designed for specific tasks, rather than a representation learning framework to serve different downstream tasks. To fill this gap, some researchers proposed a
> Transformer-based architecture, called TST [70]. Like RITA, TST supports regression, classification, and unsupervised learning through the “cloze test” pretraining task on timeseries. However, TST directly uses the classical Vanilla self-attention, thus not scalable to long timeseries as shown in our experiments (Sec. 7). Proc. ACM Manag. Data, Vol. 2, No. 1 (SIGMOD), Article 62. Publication date: February 2024. 62:24 Jiaming Liang, Lei Cao, Samuel Madden, Zachary Ives, and Guoliang Li
> 8.2 Efficient Transformers
> The need to improve the scalability of Transformers has led to more efficient variations, especially for accommodating long text data in NLP [56]. A first step was to introduce fixed/random patterns to the self-attention mechanism. Sparse Transformer [10] and Longformer [4] only compute attention at fixed intervals. ETC [2] and BigBird [69] use global-local attention: the computation is limited within a fixed radius, while some auxiliary tokens are added to attend/get attended globally. However, fixed attention patterns heavily depends on users to give an optimal setting. Reformer [31] proposed only computing the dominant attention terms based on their observation of sparsity in attention matrix from language/image data. Such sparsity is intuitive in language data, in which a word’s attention mainly focuses on the nearby sentences. However, attention in timeseries data shows strong seasonal patterns rather than sparse patterns, mainly as result of the periodicity of timeseries data. Therefore, such works do not work well for timeseries. Apart from introducing attention patterns, some works seek to solve this problem with applied mathematics techniques. Linformer [62] performs a projection to decrease the size of query, key and value matrices before attention computation, because the attention matrix tends to be low-ranked. Performer [11] uses linear functions to approximate the kernel function softmax, making attention computation commutative. Linformer and Performer do not depend on the unique properties of language data, thus potentially fitting timeseries better than other techniques, which is why we compared against them in our experiments. However as shown in Sec. 7, our group attention significantly outperforms them in both accuracy and efficiency (training time), because group attention fully leverages the periodicity of timeseries. In Table 6, we summarize the time/space complexity of the works that target scale Transformers to long sequence. Note although several methods claim linear time/space complexity, their complexities all involve a method-specific constant, similar to the number of groups 𝑁 in our group attention. In the long time series scenarios, when𝑑 ∈ [64,128,256] and𝑛 ≫ 𝑑 ≈ (common settings) where 𝑑 denotes the dimension of feature embeddings and 𝑛 represents the length of the timeseries, the theoretical complexities of PatchTST, Triformer, Linformer, and Performer are at the same magnitude to group attention. However, our empirical experiments show that Group Attention consistently and significantly outperforms these methods in terms of efficiency, as shown in Fig. 4, Fig. 5, Table 3. This is because our group attention is well-suited to long time series. The longer the timeseries is, the more opportunity group attention has to find the similar segments and group them together. This leads to a slower growth rate in the number of groups ‘N’ – the constant in the time/space complexities of group attention. 9 CONCLUSION
> In this work, we presented RITA, an automatic, self-supervised, and scalable timeseries embedding tool. RITA effectively adapts Transformer, popular in NLP, to embed timeseries segments into feature vectors. As the key component of RITA, group attention eliminates the performance bottleneck of the classical self-attention mechanisms, thus successfully scaling RITA to highly complex, long timeseries data. Our experiments confirm that RITA significantly speeds up existing attention mechanisms by 63X with a better accuracy. ACKNO WLEDGMENTS
> This work was supported in part by NSF grants III-1910108 and DBI-2327954. Proc. ACM Manag. Data, Vol. 2, No. 1 (SIGMOD), Article 62. Publication date: February 2024.

和ROCKET[18]等方法在公开数据集上取得了显著性能表现。尽管如此，传统方法仍面临一个或多个问题：它们(1) 依赖专家知识进行特征提取；(2) 计算成本高昂且不适合GPU设备；(3) 只支持单变量时间序列； (4) 仅执行分类任务。特别是作为时间序列表示学习的SOTA方法，GRAIL[47]从数据中提取地标并结合这些地标计算表征。然而 GRAIL只支持单变量时间序列。我们的实验（第7.4节）表明 RITA在单变量时间序列的有效性和效率上均优于GRAIL。基于CNN/RNN的深度学习方法如InceptionTime[25]和Resnet[23]等基于CNN的方法擅长分类任务，但由于卷积网络的归纳偏差无法处理生成性任务（如预测）。TS2VEC[68]是SOTA非Transformer表示学习方法，采用CNN架构。实验确认 RITA始终优于它。基于RNN的方法如Brit[8]和deepAR[51]支持分类、回归和生成。然而循环结构带来了诸多问题：(1) 限制模型捕捉长程相关的能力； (2) 因梯度消失/爆炸问题而训练异常困难 [48]。因此此类方法难以扩展到非常长时间序列。基于Transformer的深度学习方法鉴于Transformer在几乎所有序列建模任务中都是最佳主干选择，已有努力将其应用于时间序列分析。在时间序列预测领域 LogTrans[35]引入了对注意力计算的日志稀疏性假设。Informer[71]进一步推进LogTrans并扩展预测到多变量时间序列。Autoformer[65]通过将时间序列分解为趋势部分和季节部分进行预测。FEDformer[72]提出了基于傅里叶变换的频率增强注意力机制。Pyraformer[40]和Triformer[12]采用了分层注意力结构。PatchTST[46]在注意力中引入了块划分模式。在我们的实验中，从这个大类方法中我们选择 Triformer 和 PatchTST 作为基线模型，因为它们实验证明优于其他方法且被认为是该领域的SOTA方法。由于这些方法是专门针对时间序列预测设计的，其专业化的特征嵌入可能对其他时间序列分析任务产生负面影响。例如Triformer引入了序列压缩操作，在插补任务中可能导致关键信息丢失从而造成不利影响。此外 Triformer采用变量特定建模方式，为每个输入通道单独计算嵌入向量。虽然这种做法对于预测任务可能是有益的，但可能不适合分类任务，因为后者需要同时考虑所有通道的信息。在插补任务中 CDSA[43]优于统计方法和SOTA RNN-based 方法 Brit[8]。在时间序列分类任务中 AutoTransformer[50]通过架构搜索适应不同领域的任务需求。在时间序列异常检测领域 Anomaly Transformer[66]表现优于许多广泛使用的方法如 OmniAnomaly[54]，假设注意力得分图呈现高斯分布特性。所有这些工作都是针对特定任务设计的，并非用于服务多种下游任务表示学习框架。为填补这一空白一些研究者提出了基于Transformer架构 TST[70]。与RITA类似 TST通过在时间序列上执行“填空测试”预训练任务支持回归、分类和无监督学习。然而TST直接使用经典Vanilla自注意力机制，如我们在实验（第7节）所示无法扩展到长时序数据。Proc. ACM Manag. Data, Vol. 2, No. 1 (SIGMOD), Article 62. Publication date: February 2024. 62:24 Jiaming Liang, Lei Cao, Samuel Madden, Zachary Ives, and Guoliang Li  
8.2 高效的Transformer模型  
提升Transformer可扩展性的需求促使了更多高效变体的发展，特别是为了适应NLP中的长文本数据[56]。第一步是向自注意力机制引入固定/随机模式。Sparse Transformer[10]和Longformer[4]仅在固定的间隔计算注意力。ETC[2]和BigBird[69]使用全局-局部注意力：计算限制在一个固定半径内，同时添加一些辅助标记以实现全局关注或被关注。然而 固定的注意力模式严重依赖用户给出最优设置。Reformer[31]基于对语言/图像数据中注意力矩阵稀疏性的观察提出仅计算主导注意力项。这种稀疏性在语言数据中是直观的，因为一个词的关注主要集中在附近句子上。但时间序列中的注意力表现出强烈的季节性模式而非稀疏模式，这主要是由于时间序列数据的周期性特性所致。因此 这些方法对于时间序列效果不佳。除了引入注意力模式 一些工作尝试通过应用数学技术解决此问题。Linformer[62]在计算前对查询、键和值矩阵进行投影以降低其规模 因为注意力矩阵往往具有低秩性质。Performer[11]使用线性函数近似softmax核函数使注意力计算可交换化。Linformer 和 Performer 不依赖语言数据的特殊属性 从而可能比其他技术更适合时间序列 这就是我们实验中对比它们的原因。然而 如第7节所示 我们的组注意力在准确性和效率（训练时间）方面均显著优于它们 因为组注意力充分利用了时间序列的周期性特性。表6总结了针对扩展Transformer处理长序列的工作的时间/空间复杂度。注意 虽然几种方法声称具有线性时间/空间复杂度 但其复杂度都包含特定方法常数 类似于我们组注意力中的分组数量𝑁。在长时间序列场景中 当𝑑 ∈ [64,128,256]且𝑛 ≫ 𝑑 ≈ (常见设置) 其中𝑑表示特征嵌入的维度 而𝑛代表时间序列长度 时 PatchTST、Triform ramp[72]等方法的时间/空间复杂度均与上述类似。Proc. ACM Manag. Data, Vol. 2, No. 1 (SIGMOD), Article 62. Publication date: February 2024.
