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

RITA: Group Attention is All You Need for Timeseries Analytics  
JIAMING LIANG, University of Pennsylvania, USA  
LEI CAO, Uof Arizona/MIT, USA  
SAMUEL MADDEN, Massachusetts Institute of Technology, USA  
ZACHARY IVES, University of Pennsylvania, USA  
GUOLIANG LI, Tsinghua University, China  
时间序列分析在许多现实应用中至关重要。最近，Transformer模型（最初用于自然语言处理）已被用来从时间序列数据中学到高质量的特征嵌入：这些嵌入是各种时间序列分析任务性能的关键因素，例如向量数据库中的基于相似性的时序查询。然而，二次时间和空间复杂度限制了Transformers的可扩展性，尤其是在长时序场景中。为了解决这些问题，我们开发了一个时间序列分析工具RITA，它使用了一种新颖的注意力机制——称为组注意力（group attention）来解决这一可扩展问题。组注意力根据对象之间的相似性动态地将它们聚合成少量的组，并在粗粒度组级别近似计算注意力。因此显著降低了时间和空间复杂度，同时提供了对所计算注意力质量的理论保证。RITA的动态调度器持续调整训练过程中所需的分组数量和批量大小，确保组注意力始终使用最少的分组以满足近似精度要求。广泛的实验表明，在各种时间序列数据集和分析任务中，RITA在准确率上优于现有技术，并且显著更快——速度提升高达63倍。CCS Concepts: • 信息系统 → 数据管理系统。附加关键词：时序分析、自监督学习、注意力机制、高效Transformer  
ACM参考文献格式：Jiaming Liang, Lei Cao, Samuel Madden, Zachary Ives and Guoliang Li. 2024. RITA: Group Attention is All You Need for Timeseries Analytics. Proc. ACM Manag. Data 2, 1 (SIGMOD), Article 62（February 2024），28页。https://doi.org/10.1145/3639317  
1 引言  
许多数据驱动的应用涉及处理大规模时间序列数据，包括物联网[14]、医学人工智能[17]、股票市场[32]等。因此，对时序分析有巨大需求，例如预测[9]、分类[24]、聚类[36]、相似性搜索[45]和异常检测[57]，其应用范围从自动诊断疾病[6]到识别人类活动[34]以及阻止金融欺诈[67]。特别是，在数据库领域，向量数据库[61]被用于存储和索引非结构化及半结构化数据的高维特征嵌入，这允许用户  
作者地址：Jiaming Liang, University of Pennsylvania, Philadelphia, PA, USA, liangjm@seas.upenn.edu; Lei Cao, Uof Arizona/MIT, Tucson, AZ, USA, lcao@csail.mit.edu; Samuel Madden, Massachusetts Institute of Technology, Cambridge, MA, USA, madden@csail.mit.edu; Zachary Ives, University of Pennsylvania, Philadelphia, PA, USA, zives@cis.upenn.edu; Guoliang Li, Tsinghua University, Beijing, China, liguoliang@tsinghua.edu.cn。本工作采用知识共享署名国际4.0许可协议。© 2024 版权由原作者/持有者所有。ACM 2836-6573/2024/2-ART62 https://doi.org/10.1145/3639317

> Timeseries Dataset
> Store
> Provide
> (Embedding, Timeseries)
> Timeseries as (key, value)

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
> Fig. 1. RITA in a timeseries-based query system to efficiently explore this data by conducting similarity searches in the embedding space. Effective feature representations are a key building-block to construct a valid vector database. As a real-world example, we have been collaborating with a major US hospital [7] to develop a large-scale interactive system to label EEG segments (450 million segments, 30TB) with 6 classes representing different types of seizures. These labeled EEG segments are used to train a classifier which can then automatically detect seizures based on EEG signals collected during the clinical observation of patients. The goal of this system is to propagate the labels provided by the experts to similar segments, thus reducing the manual labeling efforts by the neurologists. Our timeseries feature embedding approach, RITA, functions as a core component in this system. More specifically, we use RITA to convert the EEG segments into feature embeddings and store them in a vector database which supports similarity search requests submitted by the neurologists to return the 𝑘 nearest neighbors of the to-be-labelled segment, as depicted in Fig. 1. Recently researchers [70] have started leveraging the self-supervised pre-training methodology of Transformers [5, 19, 59], which have proven remarkably successful in natural language processing (NLP), to automatically learn high quality feature embeddings from timeseries. In NLP, self-supervised pre-training exploits the sequential patterns (correlations) among the words in sentences to produce contextualized feature embeddings. Timeseries bear similarity to natural language because in timeseries data the sequential order among the values (stock price, volume, etc.) over time matters. That is, each value is highly correlated with other values observed before or after it. Therefore, pre-training a Transformer model which takes the correlations among different observations into account is a natural idea to learn feature embeddings from timeseries. Indeed, the experiments in [70] confirm that Transformer-based methods outperform traditional timeseries analytics techniques. Existing work [70] that directly applies Transformers to learn features from timeseries data has been shown not to scale to long timeseries [35]. The idea of self-attention [59] is central to pre-training methods in NLP: It computes pairwise correlations among different semantic units in a sequence (in NLP, a sentence); as such, it has quadratic time and space complexity in the length of the input sequence. This limits the model’s scalability, especially when handling large-scale timeseries data, which is common in real-world applications such as IoT, medical AI, and finance [7, 39, 71]. Predictions about timeseries may need to look at hundreds of thousands of prior samples to achieve accuracy. Referring again to our EEG project, seizures are brief, so we chunk EEG data into 2-second segments and detect seizures at the segment level. However, the classification of a particular segment depends on up to 12 hours of prior signal to consider long-term trends and determine if one 2-second segment indicates a seizure. There are more than 21,000 segments in 12 hours. This greatly exceeds the number of semantic units that typical NLP tasks expect. For example, BERT [19]

用户机器学习  
分类流式事件  
图1. RITA在基于时间序列的查询系统中用于通过在嵌入空间执行相似性搜索高效探索该数据。有效的特征表示是构建有效向量数据库的关键组成部分。作为一个现实案例，我们与一家美国主要医院[7]合作开发了一个大规模交互系统，以标记EEG段（4.5亿个片段，30TB），这些片段有6类代表不同类型的癫痫发作。这些带标签的EEG段用于训练一个分类器，该分类器可以根据临床观察患者时收集到的EEG信号自动检测癫痫发作。此系统的目的是将专家提供的标签传播至相似片段，从而减少神经科医生的手动标注工作量。我们的时间序列特征嵌入方法RITA在此系统中作为核心组件发挥作用。更具体地说，我们使用RITA将EEG段转换为特征嵌入，并存储在支持神经科医生提交的相似性搜索请求的向量数据库中，以返回待标记片段的k个最近邻，如图1所示。近期研究人员[70]开始利用Transformer模型的自监督预训练方法（5, 19, 59），该方法已在自然语言处理(NLP)领域取得了显著成功，从而自动从时间序列数据中学习高质量特征嵌入。在NLP中，自监督式预训练通过句子中的词语之间的顺序模式(相关性)生成上下文化的特征嵌入。时间序列与自然语言相似之处在于，在时间序列数据中随时间变化的值（股票价格、成交量等）的顺序至关重要。也就是说，每个值与其他前后观测到的值高度相关。因此，预训练一个考虑不同观察之间关联性的Transformer模型是学习时间序列特征嵌入的一种自然想法。实际上，[70]中的实验确认了基于Transformer的方法优于传统的时间序列分析技术。现有工作[70]直接应用Transformer从时间序列数据中学习特征已被证明无法扩展到长时序[35]。自注意力机制[59]的思想是NLP预训练方法的核心：它计算序列（在NLP中为句子）不同语义单元之间的成对相关性；因此，其时间和空间复杂度与输入序列长度呈二次关系。这限制了模型的可扩展性，尤其是在处理大规模时间序列数据时，这类数据常见于物联网、医学人工智能和金融等现实应用[7, 39, 71]。关于时间序列的预测可能需要查看数以万计的历史样本才能达到准确率。再次参考我们的EEG项目，癫痫发作是短暂的，因此我们将EEG数据分块为2秒段并在段级别检测癫痫发作。然而，特定片段的分类依赖于长达12小时之前的信号来考虑长期趋势并判断某个2秒段是否表示癫痫发作。在12小时内有超过2.1万个片段。这远远超过了典型NLP任务预期的语义单元数量。例如，BERT[19]

> RITA: Group Attention is All You Need for Timeseries Analytics 62:3 limits the number of units to 512 and even massive models like GPT-3 [5] limit the number of units to 2048. Although in NLP some lower-complexity methods have been proposed to approximately compute self-attention [11, 31, 62], their performance degrades dramatically when used on timeseries, due to the gap between natural language and timeseries, as we will show in our experiments. Proposed Approach. To tackle the aforementioned problem, we develop RITA, a Transformerbased timeseries analytics tool, which uses a novel attention mechanism, called group attention, to scale to long timeseries. Our goal is to significantly speed up execution versus prior methods while sacrificing minimal predictive accuracy. Leveraging the similarity among long timeseries pieces, RITA chunks the input timeseries into segments and dynamically clusters the segments into a small number (denoted as 𝑁 ) of groups. Segments in the same group possess similar feature embeddings during the current training iteration, enabling them to approximately share the computation of attention. As the timeseries increases in length, more sharing opportunities become available.

RITA: Group Attention is All You Need for Timeseries Analytics 62:3限制了单位数至512，甚至大规模模型如GPT-3[5]也仅限于2048个单位。尽管在NLP中一些低复杂度方法已被提出以近似计算自注意力[11, 31, 62]，但由于自然语言与时间序列之间的差异，在我们的实验中这些方法的性能会显著下降。提出的方案：为了解决上述问题，我们开发了RITA，一个基于Transformer的时间序列分析工具，它使用一种新颖的注意力机制——组注意力（group attention）来扩展到长时序数据。我们的目标是在保持最小预测精度损失的前提下显著加速执行速度。利用长时间序列片段之间的相似性，RITA将输入时间序列分块为段，并动态地将其聚合成少量（记作N）个组。同一组中的段在当前训练迭代中具有类似的特征嵌入，使它们能够近似共享注意力计算。随着时序长度的增加，更多的共享机会变得可用。

> As the timeseries increases in length, more sharing opportunities become available. RITA then computes self-attention at a group level and produces a compressed group attention matrix. In this way, group attention eliminates both computation and memory bottlenecks in Transformer-style models, and thus more scalable to long timeseries. However, making this idea effective and efficient in Transformer architectures is challenging for several reasons:
> • Efficiently producing high quality feature embeddings. RITA computes the attention matrix at a group level. To preserve the quality of the feature embeddings, it still has to produce different embeddings for different segments. This is because even if some segments share the attention score temporally, they may not share the same feature embedding. Using the group attention matrix, the existing self-attention mechanism will produce only a single feature vector for each group. Anaive solution would be to restore the original attention matrix from the group attention matrix. However, in this case, we again get an attention matrix with quadratic space complexity. Because GPUs have limited memory, GPU memory will remain a bottleneck in group attention. • The number of groups N. In RITA, the number of groups 𝑁 is a crucial factor that balances the speedup and quality of attention approximation. A small 𝑁 will lead to a large speedup, but the approximation errors can also be significant. On the other hand, although a large 𝑁 tends to produce high-quality approximations, it inevitably slows down the training process. Therefore, an appropriate 𝑁 is essential to the performance of group attention. However, 𝑁 depends on the distributional properties of the dataset. Furthermore, like the classical transformer models, RITA stacks multiple attention layers to produce better embeddings. Ideally, different layers should also use different values of 𝑁 . In addition, during the model training phase, group attention should use different values of 𝑁 in different iterations to adapt to the varying feature embeddings. This makes manually optimizing 𝑁 almost impossible. • Batch size. Moreover, as we want to dynamically adjust 𝑁 during training, a fixed batch size is sub-optimal: as 𝑁 decreases, the memory usage of a single sample decreases. This allows a larger batch size, which (1) makes full use of GPU memory; (2) enables parallelism across the samples. Thus, RITA should dynamically adjust the batch size as 𝑁 changes. To address the above problems, we first propose an embedding aggregation strategy and a customized group softmax function to replace the classical softmax function [59]. Together they ensure RITA able to directly use the compressed attention matrix to produce different feature embeddings for different segments. We theoretically show that the embeddings RITA produces in this way are identical to those produced by first re-storing the original large attention matrix. Thus
> RITA produces high-quality embeddings without introducing extra overhead. Second, we design an adaptive scheduler that dynamically decides an appropriate 𝑁 for each group attention layer during the training process. It starts with a large 𝑁 and iteratively merges groups that are similar to each other. Guided by an error bound on the approximated self-attention that users can tolerate, it automatically determines if two groups are mergeable, performing merging efficiently in a GPU-friendly way. Moreover, we propose a learning-based method to model the correlation between the number of groups 𝑁 and the batch size 𝐵. This model predicts 𝐵 for a given 𝑁 when training RITA. Specifically, we first sample some 𝑁 values in a reasonable range. For each sampled 𝑁 , we find a batch size that consumes up to a certain percentage of GPU memory in a cost-efficient way. Using a small set of mathematical functions as a prior, RITA is able to learn a model with only a few ⟨𝑁 , 𝐵⟩ pairs as ground truth labels. Our experiments on public timeseries benchmarks and the MGH EEG data [7] confirm that compared to existing self-attention mechanisms [11, 12, 46, 59, 62], our group attention mechanism achieves a 63X speedup with much less memory required with comparable or even better accuracy on various timeseries analytics tasks. Contributions. The key contributions of this work include:
> • Our group attention mechanism reduces the time and space complexity of the self-attention mechanism with accuracy guarantees, allowing RITA to scale to long timeseries data. • Guided by an approximation error bound, our adaptive scheduler dynamically adapts the number of groups and the batch size to the distribution properties of the evolving feature embeddings, making group attention efficient and easily tunable. • We conduct experiments on various datasets and analytics tasks, demonstrating that RITA is 4 to 63 times faster than the existing Transformer-based approaches while achieving comparable or better accuracy when handling long timeseries (length ≥ 2000). 2 BACKGROUND
> We provide some background on the canonical self-attention module in the Transformer [59]. takes 𝑛 hidden embedding vectors 𝐻 ∈ R𝑛∗𝑑ℎ as input, then projects them to queries
> Self-attention
> (𝑄 ), keys (𝐾 ) and values (𝑉 ) and performs Scaled-dot Product Attention, which given input hidden state 𝐻 , is computed by:
> 𝑄 = 𝐻𝑊 , 𝐾 = 𝐻𝑊 , 𝑉 = 𝐻𝑊 , 𝑂 = 𝐴𝑉 = 𝑆𝑜 𝑓 𝑡 𝑀𝑎𝑥 ( )𝑉 (1)
> 𝑄 𝐾 𝑉 √︁ 𝑑 𝑘
> Where 𝑊 ∈ R𝑑ℎ ∗𝑑𝑘 , 𝑊 ∈ R𝑑ℎ ∗𝑑𝑘 , 𝑊 ∈ R𝑑ℎ ∗𝑑𝑣 are projection matrices for generating 𝑄, 𝐾 , 𝑉 . 𝑄 ∈ R𝑛∗𝑑𝑘 is also regarded as the packing of 𝑛 query vectors {𝑞 , ..., 𝑞 } with dimension 𝑑 into
> 1 𝑛 𝑘 a matrix. 𝐾 ∈ R𝑛∗𝑑𝑘 , 𝑉 ∈ R𝑛∗𝑑𝑣 are regarded as the packing of key vectors {𝑘 , ..., 𝑘 } and value
> 1 𝑛 vectors {𝑣 , ..., 𝑣 } in the same way. Given a matrix 𝑀 ∈ R𝐿∗𝑛 , the softmax function normalizes 𝑀 to ensure the sum of each row equals to 1, as shown below. 𝑒𝑥 𝑝 (𝑀 ) 𝑖, 𝑗
> 𝑆𝑜 𝑓 𝑡 𝑀𝑎𝑥 (𝑀 ) = (2) 𝑖, 𝑗 𝑛 1
> − 𝑒𝑥 𝑝 (𝑀 ) 𝑘 =0 𝑖,𝑘
> 3 RITA OVERVIEW
> Given a collection of unlabeled timeseries, RITA first pre-trains a Transformer-style model to produce high quality feature embeddings. This pre-trained model is then used to support various downstream tasks with minimal modifications to the model architecture, aligned with the design philosophy of BERT [19]. RITA: Group Attention is All You Need for Timeseries Analytics 62:5
> ..... O O O O
> 0 1 2 n
> RITA Encoder
> E E E ..... E
> 0 1 2 n
> Position P ..... P
> P P
> Embedding 0 1 2 n
> + + + +
> Window W W W W
> [CLS] 1 2 ..... n
> Embedding
> ..... Time-aware
> Convolution
> Scale & Input
> Raw Timeseries
> Fig. 2. RITA architecture
> Next, we use an example to show how RITA supports a timeseries query system in Sec. 3.1, followed by an overview of the RITA model architecture in Sec. 3.2. We will provide a detailed illustration on how RITA addresses a range of downstream tasks in Sec. 6. 3.1 RITA in Timeseries Query Systems
> Fig. 1 shows a Seizure Diagnosis System we have been developing for a major US hospital. RITA is used both in the training stage and the deployment stage. As described in the Introduction, we use
> RITA to encode the EEG segments and store the resulting (timeseries, embedding) pairs in a vector database as (key, value) pairs. This is used to for similarity-based labeling. Thereafter, we train a classification model by fine-tuning the RITA model and deploy it in the patient monitoring system to detect seizures at real time. Once a new EEG segment arrives, the system uses the RITA encoder to embed it into a feature embedding, and thereafter classifies it into one type of seizures. 3.2 Model Architecture
> As shown in Fig. 2, RITA consists of two components: (1) Time-aware Convolution Layer and (2)
> RITA Encoder. Time-aware Convolution Layer fills the gap between timeseries and natural language.

RITA随后在组级上进行自注意力计算并生成压缩后的组注意力矩阵。通过这种方式，组注意力消除了基于Transformer模型的计算和内存瓶颈，因此更适用于长时序数据。然而，在Transformer架构中使这一思想有效且高效面临以下挑战：  
• 高效产生高质量特征嵌入。RITA在组级上计算注意力矩阵。为了保持特征嵌入的质量，它仍需为不同段生成不同的嵌入。这是因为即使某些片段在时间维度上共享注意力得分，它们可能并不具有相同的特征嵌入。使用组注意力矩阵时，现有的自注意力机制将为每个组仅产生一个特征向量。一种朴素的解决方案是通过组注意力矩阵恢复原始注意力矩阵。然而，在这种情况下我们再次得到空间复杂度呈二次关系的注意力矩阵。由于GPU内存有限，GPU内存将成为组注意力的主要瓶颈。  
• 组的数量𝑁。在RITA中，组数量𝑁是一个关键因素，它平衡了加速效果与注意力近似质量之间的权衡。较小的𝑁会导致较大的加速效果，但近似误差也可能显著增加。另一方面，虽然较大的𝑁倾向于产生高质量的近似结果，但它不可避免地会减缓训练过程。因此，合适的𝑁对组注意力性能至关重要。然而，𝑁依赖于数据集的分布特性。此外，与经典Transformer模型类似，RITA堆叠多个注意力层以生成更好的嵌入。理想情况下，不同层数应使用不同的𝑁值。另外，在模型训练阶段，组注意力应在不同迭代中采用不同的𝑁值来适应变化的特征嵌入。这使得手动优化𝑁几乎不可能。  
• 批量大小。此外，由于我们希望在训练过程中动态调整𝑁，固定的批量大小是次优选择：随着𝑁减小，单个样本的内存使用减少。这允许更大的批量尺寸，其（1）充分利用GPU内存；（2）实现跨样本并行性。因此，RITA应根据𝑁的变化动态调整批量大小。为了解决上述问题，我们首先提出一种嵌入聚合策略和定制化的组softmax函数以替代经典softmax函数[59]。它们共同确保RITA能够直接使用压缩后的注意力矩阵生成不同段的特征嵌入。我们在理论上证明了RITA通过这种方式产生的嵌入与先恢复原始大尺寸注意力矩阵后得到的结果完全一致。因此，RITA在不引入额外开销的情况下产生高质量嵌入。其次，我们设计了一种自适应调度器，在训练过程中动态决定每个组注意力层的合适𝑁值。它从较大的𝑁开始，并迭代地合并相似度高的组。根据用户可容忍的近似自注意力误差界限进行指导，自动判断两个组是否可以合并，并以GPU友好的方式高效执行合并操作。此外，我们提出了一种基于学习的方法来建模组数量𝑁与批量大小𝐵之间的相关性。该模型在训练RITA时预测给定𝑁对应的𝐵值。具体而言，我们首先在一个合理范围内采样一些𝑁值。对于每个采样的𝑁，我们在成本效益上找到一个使GPU内存占用达到特定百分比的批量尺寸。利用少量数学函数作为先验知识，RITA仅需极少数⟨𝑁, 𝐵⟩对的真实标签即可学习到模型。我们的实验在公开时间序列基准数据集和MGH EEG数据[7]上的结果表明，与现有自注意力机制[11, 12, 46, 59, 62]相比，在各种时间序列分析任务中RITA实现了显著更高的加速效果（达63倍）且内存需求大幅降低，同时保持了相当或更优的准确性。贡献。本工作的关键贡献包括：  
• 我们的组注意力机制在保证精度的前提下降低了自注意力机制的时间和空间复杂度，使RITA能够扩展到长时序数据。  
• 受近似误差界限引导，我们的自适应调度器动态调整组数量与批量大小以匹配演进特征嵌入的分布特性，使得组注意力高效且易于调优。  
• 我们在多种数据集和分析任务上进行了实验，证明RITA比现有基于Transformer的方法快4到63倍，在处理长时序（长度≥2000）时实现了相当或更优的准确性。

**背景**  
我们提供关于Transformer中经典自注意力模块的一些背景知识[59]。该模块输入𝑛个隐藏嵌入向量𝐻 ∈ Rⁿ×𝑑ℎ，然后将其投影到查询（𝑄）、键（𝐾）和值（𝑉），并执行缩放点积注意力计算。给定输入隐状态𝐻，其计算方式为：  
𝑄 = 𝐻𝑊ₖ, 𝐾 = 𝐻𝑊ₖ, 𝑉 = 𝐻ぶ, 其中𝑊ₖ ∈ R𝑑ℎ×𝑑𝑘、𝑊ᵥ ∈ R𝑑ℎ×𝑑𝑣。注意力矩阵的计算公式为：  
softmax_max(𝑀) = (exp(Mᵢⱼ)) / (∑ exp(Mᵢᵏ)), 该式中的分母对所有k求和，i,j表示当前元素位置。

**RITA概览**  
给定一组未标记的时间序列数据，RITA首先预训练一个基于Transformer的模型以生成高质量特征嵌入。此预训练模型随后用于支持各种下游任务，并通过最小修改模型架构实现，这与BERT[19]的设计哲学一致。图2展示了RITA体系结构：

**图2. RITA架构**  
接下来我们用示例说明RITA如何在第3节中支持时间序列查询系统，然后概述RITA模型的总体架构。我们在第6节将详细阐述RITA如何处理多种下游任务。  
**3.1 在时序查询系统中的RITA应用**  
图1展示了我们为一家美国主要医院开发的癫痫诊断系统。RITA既用于训练阶段也用于部署阶段。如引言所述，我们使用RITA对EEG片段进行编码，并将生成的（时间序列, 嵌入）对存储在向量数据库中作为（键, 值）对以支持基于相似性的标签分配。随后通过微调预训练模型来训练分类器，并部署到患者监测系统中实现癫痫实时检测。当新到达一个EEG片段时，系统使用RITA编码器将其嵌入为特征嵌入后进行分类并归类至某一种癫痫类型。  
**3.2 模型架构**  
如图2所示，RITA包含两个组件：（1）时间感知卷积层和（2）RITA编码器。时间感知卷积层填补了时序数据与自然语言之间的鸿沟。

> Time-aware Convolution Layer fills the gap between timeseries and natural language. Despite their high-level similarity, there is a big gap between timeseries and natural language. First, in natural language each word, as a discrete semantic unit, has an independent meaning, while each element in a timeseries is a continuous, numerical value and does not necessarily constitute an independent event. Furthermore, the input sequences are single-channeled in NLP, but often multi-channeled in timeseries (i.e., sensor data often consists of several related channels). RITA leverages the classical convolution [33] strategy to solve this problem. Convolution is widely used to capture the local structures of an image. We use convolution to chunk one input timeseries into a sequence of windows and learn the local structure of each window, similar to the discrete semantic units in natural language. It also discovers the correlations across different channels, thus naturally solving the multi-channel problem. More specifically, treating a multi-variate timeseries of length 𝑛 and with 𝑚 variables as an n × m matrix 𝑇 , RITA uses 𝑑 convolution kernels to chunk 𝑇 into n windows and produce one ddimensional embedding per window using the convolution operation [33]. Each convolution kernel corresponds to a w × m matrix, where 𝑤 defines the number of timestamps that each convolution kernel covers, identical to the window size in sliding window. takes the embeddings of 𝑛 semantic units 𝑋 , 𝑋 , ..., 𝑋 (𝑋 ∈ 𝑅𝑑 ) as input (e.g.
> RITA Encoder 1 2 𝑛 𝑖 embeddings of 𝑛 windows for a timeseries), then models the correlations between the semantic units and outputs 𝑌 , ..., 𝑌 (𝑌 ∈ 𝑅𝑑 ) as the context-aware embedding of each unit. What makes RITA Encoder different from Transformer Encoder is that: at the core of Transformer
> Encoder lies self-attention mechanism which incurs a 𝑂 (𝑛2) time complexity and memory usage. This quadratic cost becomes prohibitive for long timeseries and limits the scalablity of Transformerbased models. To make the attention computation efficient yet high-quality, we replace the canonical self-attention with our proposed group attention. Self-supervised Pretraining. Inspired by the “cloze text” pretraining task in NLP, we designed a mask-and-predict task as the pretraining task for our model. The timeseries is randomly masked and the model should recover the masked values based on corresponding contextual information. To be specific, we generate masks on time-stamps, with a mask rate 𝑝 . The timeseries is scaled to be non-negative and the values across all the channels on the masked timestamps are set to be
> -1, an impossible value on normal timestamps. Then the masked timeseries is fed into RITA and the output representation is translated to the recovered timeseries by a Transpose Convolution layer. 4 GROUP AT TENTION MECHANISM
> Group attention, a novel and efficient approximate attention mechanism, addresses the performance bottleneck of self-attention in the vanilla Transformer. In this section, we first introduce the framework of group attention and then theoretically establish the bound of its approximation error. We use examples to explain the group attention mechanism, as depicted in Figure 3. 4.1 The Idea of Group Attention
> As periodicity is a natural property of timeseries [64], similar windows frequently occur. Similar windows result in similar queries/keys for attention computation, bringing opportunities for saving computation. As discussed in Sec. 2, 𝐴 , the attention score of window 𝑖 onto window 𝑗 , is determined by the 𝑖 𝑗 inner product between the query vector of window 𝑖 and the key vector of window 𝑗 , that is, 𝑞 · 𝑘 . Given another window 𝑥 , if window 𝑥 has a key vector similar to that of window 𝑗 , that is, 𝑘 ≈ 𝑘 , 𝑗 𝑥 then 𝑞 · 𝑘 ≈ 𝑞 · 𝑘 . In other words, 𝐴 ≈ 𝐴 when 𝑘 ≈ 𝑘 . 𝑖 𝑗 𝑖 𝑥 𝑖 𝑗 𝑖𝑥 𝑗 𝑥
> Example 1. As shown in Figure 3 (Part 1), the first and third timeseries windows are notably similar, consequently yielding akin key vectors (𝑘 ≈ 𝑘 ). In vanilla self-attention (Part 2), this
> 1 3 similarity leads to two closely related columns within the attention matrix, corresponding to key vectors 𝑘 and 𝑘 . 1 3
> This observation inspires our group attention mechanism. That is, we group the windows by their similarity in keys. Assuming that all windows in the same group have the same attention score onto another window 𝑘 , we then only compute the attention once by using one single key to represent this group, for example the centroid of the group of keys. Thus, this saves significant computation cost. Better yet, after grouping 𝑛 windows into 𝑁 groups, group attention compresses the attention matrix from an 𝑛 × 𝑛 matrix to an 𝑛 × 𝑁 matrix. Because 𝑁 (number of groups) tends to be much smaller than 𝑛 (number of windows) due to the periodicity of timeseries, group attention consumes

如图2所示，RITA包含两个组件：（1）时间感知卷积层和（2）RITA编码器。时间感知卷积层填补了时序数据与自然语言之间的鸿沟。尽管它们在高层面上具有高度相似性，但时序数据与自然语言之间仍存在显著差距。首先，在自然语言中每个词作为独立的语义单元具有独立含义，而时序数据中的每个元素是连续数值且不一定构成独立事件。此外，NLP输入序列通常是单通道的，但在时间序列中往往是多通道（即传感器数据通常包含多个相关通道）。RITA利用经典卷积[33]策略解决此问题。卷积广泛用于捕捉图像局部结构。我们使用卷积将一个输入时序分割为一系列窗口并学习每个窗口的局部结构，类似于自然语言中的离散语义单元。它还发现不同通道间的关联性，从而天然地解决了多通道问题。更具体地说，将长度为𝑛且具有𝑚变量的多元时间序列视为n × m矩阵𝑇 ，RITA使用𝑑个卷积核对𝑇进行分割生成每个窗口的d维嵌入（通过卷积操作[33]）。每个卷积核对应一个w × m矩阵，其中𝑤定义了每个卷积核覆盖的时间戳数量，等同于滑动窗口大小。取𝑛个语义单元𝑋₁, 𝑋₂,..., 𝑋ₙ (𝑋 ∈ Rᵈ)的嵌入（例如RITA编码器对时序的n个窗口嵌入），然后建模语义单元间的关联性并输出𝑌₁,...,𝑌ₙ (𝑌 ∈ Rᵈ)作为每个单元的情境感知嵌入。使RITA编码器区别于Transformer编码器的是：在Transformer编码器核心是自注意力机制，其时间复杂度和内存消耗为𝑂(𝑛²)，这种二次成本对于长时序变得不可行且限制了基于Transformer模型的可扩展性。为了实现高效而高质量的注意力计算，我们将经典自注意力替换为我们提出的组注意力。  
自我监督预训练。受NLP中“cloze text”预训练任务启发，我们设计了一个掩码-预测任务作为模型的预训练任务。时序数据被随机掩码，并基于相应上下文信息恢复掩码值。具体而言，在时间戳上生成掩码（mask rate为𝑝）。将时序缩放至非负并设置所有通道在掩码时间戳上的值为-1，这是正常时间戳不可能的值。随后将掩码后的时序输入RITA，并通过转置卷积层将输出表示转换为恢复的时序数据。  
4 组注意力机制  
组注意力是一种新颖且高效的近似注意力机制，解决了vanilla Transformer中自注意力性能瓶颈问题。

> RITA: Group Attention is All You Need for Timeseries Analytics 62:7 much less memory than the original self-attention mechanism, successfully eliminating the memory bottleneck. Note that this minimally impacts quality, as confirmed in our experiments (Sec. 7.2). 1 Producing Key, Query, Value Embeddings k1, q1, v1 k2, q2, v2 k3, q3, v3 k4, q4, v4 k, q, v ∈ R1*d
> 2 Vanilla Self-Attention k1 k2 k3 k4 v1 q v2 O1
> 1 -0.43 0.68 -0.38 0.39 0.14 0.41 0.14 0.31 × v3 O2 q2 0.24 -0.70 0.28 0.11 SoftMax 0.30 0.12 0.31 0.27 v4
> O3 q3
> -0.40 0.64 -0.38 0.37 (row sum = 1) 0.14 0.40 0.15 0.31 O4 q Output ∈ Rn*d
> 4 0.19 -0.14 0.21 0.12 0.27 0.19 0.28 0.26
> Dot Product ∈ Rn*n Attention Matrix ∈ Rn*n
> 3 Group Attention
> Detects Similar Key Embeddings: k1 ≈ k3
> Aggregate Key Embeddings: (k1+k3)/2 k(1,3)
> Aggregate Value Embeddings: v1+v3 v(1,3) k(1,3) k2 k4 v
> (1,3) q Group SoftMax 0.14 0.41 0.31 v O1
> 1 -0.41 0.68 0.39 2 q Column k(1,3) counts twice 0.30 0.12 0.28 × v O2
> 2 4
> 0.26 -0.70 0.11 O3 q3 0.14 0.40 0.32
> -0.39 0.64 0.37 (row sum = 1) O4 q 0.14 0.40 0.32 n*d
> 4 Output ∈ R
> 0.20 -0.14 0.12 0.27 0.20 0.26 n*N Group Attention Matrix ∈ Rn*N
> Dot Product ∈ R
> Fig. 3. Group Attention vs. Vanilla Self-Attention
> 4.2 Computing the Output Feature Embedding
> We now discuss how to efficiently compute the output feature embeddings using the small compressed group attention matrix. 4.2.1 Problem: Producing Embeddings with the Group Attention Matrix
> As described in the Background (Sec. 2), once we have acquired the attention matrix 𝐴, canonical self-attention computes the output embedding 𝑂 as O = AV . Because 𝐴 is an 𝑛 × 𝑛 matrix and
> 𝑉 is an 𝑛 × 𝑑 matrix, the matrix product operation still produces an 𝑛 × 𝑑 matrix 𝑂 . That is, 𝑣 𝑣 it produces a 𝑑 dimensional feature vector for each window. However, our group attention will 𝑣 produce an 𝑛 × 𝑁 attention matrix 𝐴 , where 𝑁 corresponds to the number of groups. In this case

4.2 计算输出特征嵌入  
我们现在讨论如何利用压缩后的小组注意力矩阵高效计算输出特征嵌入。  
4.2.1 问题：使用组注意力矩阵生成嵌入  
如背景（第2节）所述，一旦获得注意力矩阵𝐴 ，经典自注意力通过𝑂 = 𝐴𝑉 计算输出嵌入𝑂 。因为𝐴 是𝑛 × 𝑛 矩阵且𝑉 是𝑛 × 𝑑 矩阵，矩阵乘法操作仍产生一个𝑛 × 𝑑 的矩阵𝑂。即为每个窗口生成𝑑 维特征向量。然而我们的组注意力将生成一个𝑛 × 𝑁 注意力矩阵𝐴 ，其中𝑁 对应分组数量。在这种情况下  
矩阵相乘会产生一个𝑁 × 𝑑 矩阵𝑂 。即为每组生成一个特征向量。但我们的目标是针对不同窗口产生不同的嵌入，因为即使某些窗口在时间上共享注意力得分，并不意味着它们应该具有相同的特征嵌入。  
朴素解法。一种朴素的解决方案是从小组注意力矩阵𝐴 重建完整注意力矩阵𝐴。

> the matrix product will produce a 𝑁 × 𝑑 matrix 𝑂 . That is, it produces a feature vector for each 𝑣 group. However, our goal is to produce different embeddings for different windows, because even if some windows share the attention score temporally, it does not mean they should have the same feature embedding. A Naive Solution. Anaive solution would be to restore the full attention matrix 𝐴 from the group attention matrix 𝐴. For example, given one group composed of 𝑤 𝑖𝑛 and 𝑤 𝑖𝑛 , we map its group 𝑖 𝑗 attention vector in 𝐴 into two rows that correspond to 𝑤 𝑖𝑛 and 𝑤 𝑖𝑛 in 𝐴. However, in this case 𝑖 𝑗 we again get a 𝑛 × 𝑛 attention matrix; and GPU memory remains a bottleneck in group attention. 4.2.2 Solution: Embedding Aggregation and Group SoftMax
> Using an embedding aggregation operation and a group softmax function, RITA produces 𝑛 embeddings without restoring the full attention matrix. Embedding Aggregation. The idea is inspired by the observation on the matrix product operation
> O = AV conducted on the fully restored attention matrix 𝐴.

例如，给定由𝑤ᵢₙ和𝑤ⱼₙ组成的组，将其在𝐴中的分组向量映射为对应于𝑤ᵢₙ和𝑤ⱼₙ的两行。然而在这种情况下我们再次得到一个𝑛 × 𝑛 注意力矩阵；且GPU内存仍成为小组注意力瓶颈问题。  
4.2.2 解法：嵌入聚合与组SoftMax  
通过使用嵌入聚合操作和组SoftMax函数，RITA在不重建完整注意力矩阵的情况下生成𝑛 个嵌入。嵌入聚合。该想法受对完全恢复的注意力矩阵𝐴 上进行矩阵乘法运算O = AV 的观察启发。

> O = AV conducted on the fully restored attention matrix 𝐴. Given an element 𝑂 of 𝑂 corresponding to the 𝑗 𝑡ℎ dimension of 𝑤 𝑖𝑛 ’s feature vector, 𝑂 = 𝑎 ·𝑣 , 𝑖, 𝑗 𝑖 𝑖, 𝑗 𝑖 𝑗 where vector ∈ Rn denotes the 𝑖𝑡ℎ row of the attention matrix 𝐴 and vector ∈ Rn denotes the a v i j 𝑗 𝑡ℎ dimension of all the 𝑛 feature vectors. Given =< 1, 2 , · · · , n > and =< 1, 2 , · · · , n >, a a a a v v v v i i i i j j j j
> 𝑂 = n k k . 𝑖, 𝑗 a v k=1 i j
> Example 2. As shown in Fig. 3 (Part 3), assume 𝑤 𝑖𝑛 and 𝑤 𝑖𝑛 belong to the same group 𝐺 . 1 3 1
> Then 𝑎1 = 𝑎3 = 𝑎1, where 𝑎1 ∈ 𝐴 corresponds to the attention of group 𝐺 onto 𝑤 𝑖𝑛 . Therefore, 𝑖 𝑖 𝑖 𝑖 1 𝑖 𝑎1𝑣 1 + 𝑎3𝑣 3 = 𝑎1 (𝑣 1 + 𝑣 3). So we aggregate 𝑣 = 𝑣 + 𝑣 . 𝑖 𝑗 𝑖 𝑗 𝑖 𝑗 𝑗 (1,3) 1 3
> As an immediate generalization of the above analysis, if we aggregate up the windows that belong to the same group and convert the n-dimensional feature vector 𝑣 into a 𝑁 -dimensional 𝑗 group feature vector 𝑣 beforehand, we could directly use the group attention vector 𝑎 and the 𝑗 𝑖 group feature vector 𝑣 to compute 𝑂 . 𝑗 𝑖, 𝑗
> Using embedding aggregation, RITA is able to produce the feature embedding 𝑂 that is identical

1: 函数 group_attention(Q,V,R)
2: 对于i=0→N−1执行：
3: v ← Σ_{j=0}^{n-1} (BLG==i) * v_j 
4: P←Q*R^T

> to the embedding 𝑂 produced by using the full attention matrix 𝐴 and the embedding matrix 𝑉 . Group Softmax Function. In canonical self-attention the attention matrix 𝐴 is computed as 𝐴
> = Q√K T . To compute 𝐴, we have to first compute 𝑄 𝐾𝑇 (denoted as 𝑃 ) which is an 𝑛 𝑛
> SoftMax ( ) × dk matrix. Normalizing the 𝑃 matrix with softmax produces the attention matrix 𝐴. Group attention follows the same procedure. However, after grouping keys into 𝐾 , 𝑄 𝐾𝑇 produces

5: 对于i=0→n−1执行：
6:  对于j=0→N−1执行：
7:   w ← exp(P)*CNT_{i,j}
8:  对于i=0→n−1执行：
9:    s ← Σ_{j=0}^{N-1} w_{i,j}
10: 对于i=0→n−1执行：
11: o_i ← Σ_{j=0}^{N-1} v_j * (exp(P)/s)_j
12: 返回O

> an 𝑛 × 𝑁 matrix 𝑃 . Due to the non-linearity of the softmax function, applying softmax directly on

第2-3行实现嵌入聚合操作，而第8-11行实现组softmax函数。组注意力算法的正确性证明。此处我们证明我们的高效组注意力算法（即算法1）产生的输出特征嵌入与必须首先恢复大完整注意力矩阵的朴素方法相同。进一步地：
o_i = Σ_{x=0}^{n-1}Σ_{j=0}^{N-1}(BLG==j)A_{i,x,j}v_x
= Σ_{x=0}^{n-1}Σ_{j=0}^{N-1}(BLG==j)v_x * exp(q_i·k_j)/[Σ_{k=0}^{n-1}exp(P_{i,k})]
通过结合(4),(6)(7)，我们得出：
o = Σ_{j=0}^{N-1} P_{i,j}*v_j
这证明了我们的组注意力输出与传统自注意力相同。□

> 𝑃 will result in a group attention matrix 𝐴 from which we are not able to recover a full attention

时间复杂度。算法1的时间复杂度为O(nNd)且空间复杂度为O(nN)，而原始自注意力机制的时间和空间复杂度分别为O(n²d)和O(n²)。

> matrix that is identical to first restoring 𝑃 to 𝑃 and then applying softmax on 𝑃 . The 𝐴 matrix

4.3 误差界限
组注意力产生一个近似经典自注意力产生的注意力矩阵A的组注意力矩阵A，其误差在引理4中被证明是有界的。引理4：设R为所有键向量所在球体的半径；k_i是包含键k_i的i组的代表元素。令A表示从A恢复的完整注意力矩阵。假设键k_i与k_j的距离|k_i - k_j|满足：
|k_i - k_j| ≤ d
则对于任意ε>0，若d≤(1/2R)ln(ε)，有误差界限ε=O(d²R²)。

> produced by the latter is desirable, as we want to approximate the original attention matrix as accurately as possible. However, restoring the small 𝑛 × 𝑁 𝑃 matrix is not memory efficient, as it

引理4表明组注意力的误差上限由距离d决定。如第5.1节所述，这启发我们设计一种动态确定分组数N（组注意力最关键参数）的策略。证明：由于
exp(P_{i,j}) = exp(q_i·k_j)
= exp(q_i·(k_j - k_i)) * exp(q_i·k_i) 
= exp(|q_i||k_j - k_i|cos(q_i, k_j - k_i))
因此：
exp(-dR) ≤ exp(P_{i,j}) ≤ exp(dR)
接着有：
A = Σ_{j} [exp(P_{i,j}) / (Σ_k exp(P_{i,k}))] * v_j
= Σ_{k} [exp(P_{i,k})/Σ_k exp(P_{i,k}) ] * v_k 
通过结合(9)(10)，误差被限制在：
exp(-2dR) ≤ A_{i,j}/A'_{i,j} ≤ exp(2dR)
因此，若ln(ε)/ (1/(2R)) ，则证明引理4成立。□

> will end up with a full 𝑛 × 𝑛 matrix 𝑃 . To solve the above problems, we introduce a new group softmax function to replace the original softmax function (Eq. 2). 𝑒𝑥 𝑝 (𝑃 ) 𝑖, 𝑗
> 𝐺𝑟 𝑜𝑢𝑝𝑆𝑜 𝑓 𝑡 𝑀𝑎𝑥 (𝑃 ) = (3) 𝑖, 𝑗 𝑁 1
> − 𝑐𝑜𝑢𝑛𝑡 𝑒𝑥 𝑝 (𝑃 ) 𝑘 =0 𝑘 𝑖,𝑘
> In Eq. 3, 𝑐𝑜𝑢𝑛𝑡 represents the number of windows that Group 𝐺 contains. Compared to the 𝑘 𝑘 original softmax, our group softmax considers each group 𝐺 as 𝑐𝑜𝑢𝑛𝑡 elements and counts it 𝑘 𝑘 𝑐𝑜𝑢𝑛𝑡 times when summing up the exponential of each group’s 𝑃 . For instance, in Fig. 3 (Part 𝑘 𝑖,𝑘
> 3), we count the column corresponding to 𝑘 twice in GroupSoftMax because there are two
> (1,3) elements (𝑘 , 𝑘 ) in this group. In this way, the group softmax function operating on the small 𝑃
> 1 3 matrix will produce exactly the same result to the softmax function operating on the full 𝑃 matrix. Efficient Implementation. Next, we demonstrate an efficient implementation of the embedding aggregation operation and group softmax function in Alg. 1. We denote 𝐶 𝑁 𝑇 to be the size of the 𝑖 𝑖𝑡ℎ group, 𝑁 to be the number of groups, to be the representative key of the 𝑖𝑡ℎ group and to r𝑖 Rbe the matrix consisting of all r , 𝐵𝑁 𝐺 to be the group that k belongs to. 𝑄 , 𝑉 are the packing 𝑖 𝑖 𝑖 matrices of query vectors and value vectors as described in Sec.2. Alg. 1 outputs the packing matrix
> 𝑂 for new feature emebddings {𝑜 , ..., 𝑜 }, where 𝑜 corresponds to the feature embedding of 𝑤 𝑖𝑛 . 1 𝑛 𝑖 𝑖

RITA: 组注意力在时序分析中的应用 62:11
4.4 GPU友好的分组方法
我们实现一种与K-means聚类[41]对应的分组方法，因为K-means为每个键与其组代表之间的距离提供了紧密的界限。我们设计了一种符合Transformer架构的GPU友好型K-means实现方案。K-means性能瓶颈来自向量与其中心的距离计算，即√(v_i - c_j)^2 (i∈[1,n], j∈[1,N])。相反地，
|v_i -c_j|=sqrt(|v_i|^2 + |c_j|^2 - 2v·c) 
在该公式中，性能瓶颈是v·c的计算，这可以作为矩阵乘法操作实现；而在GPU上，矩阵相乘比成对差值运算要高效得多。5 自适应调度器
接下来我们介绍RITA的自适应调度器，它解决了确定适当分组数N及相应批量大小B的问题，如引言所述。

> RITA: Group Attention is All You Need for Timeseries Analytics 62:9
> Algorithm 1 Efficient Computation of Group Attention
> Require: 𝑄, 𝑉 , 𝑅, 𝐶 𝑁 𝑇 , 𝐵𝐿𝐺
> Ensure: 𝑄, 𝑉 ∈ R𝑛∗𝑑 ,𝑅 ∈ R𝑁 ∗𝑑 ,𝐶 𝑁 𝑇 ∈ N𝑁 ,𝐵𝐿𝐺 ∈ N𝑛
> 1: function group_attention(𝑄, 𝑉 , 𝑅)
> 2: for 𝑖 = 0 → 𝑁 − 1 do
> 3: 𝑣 ← 𝑛−1 (𝐵𝐿𝐺 == 𝑖 ) 𝑣 𝑖 𝑗 =0 𝑗 𝑗
> 4: 𝑃 ← 𝑄 𝑅𝑇

> 5: for 𝑖 = 0 → 𝑛 − 1 do
> 6: for 𝑗 = 0 → 𝑁 − 1 do
> 7: 𝑤 ← 𝑒𝑥 𝑝 (𝑃 )𝐶 𝑁 𝑇 𝑖, 𝑗 𝑖, 𝑗 𝑗
> 8: for 𝑖 = 0 → 𝑛 − 1 do
> 9: 𝑠 ← 𝑁 −1 𝑤 𝑖 𝑗 =0 𝑖, 𝑗
> 10: for 𝑖 = 0 → 𝑛 − 1 do
> 𝑁 −1 𝑒𝑥 𝑝 (𝑃𝑖,𝑗 )
> 11: 𝑜 ← 𝑣 𝑖 𝑗 =0 𝑠 𝑗 𝑖
> 12: return 𝑂
> Lines 2-3 implement the embedding aggregation operation, while Lines 8-11 implement the group softmax function. The Correctness Proof of the Group Attention Algorithm. Here we prove that our efficient group attention algorithm, i.e., Alg. 1, produces the same output feature embedding with the naive method that has to first restore the big full attention matrix. Further, 𝑛 −1 𝑁 −1 𝑛 −1
> ∑︁ ∑︁ ∑︁ o = 𝐴 v = (𝐵𝑁 𝐺 == 𝑗 )𝐴 v 𝑖 𝑖, 𝑗 j 𝑥 𝑖,𝑥 𝑥 𝑗 =0 𝑗 =0 𝑥 =0
> 𝑁 −1 𝑛 −1
> ∑︁ ∑︁ 𝑒𝑥 𝑝 (q · k ) 𝑖 𝑥
> = (𝐵𝐿𝐺 == 𝑗 ) v (7) 𝑥 𝑛 1 𝑥
> − 𝑒𝑥 𝑝 (𝑃 ) 𝑗 =0 𝑥 =0 𝑘 =0 𝑖,𝑘
> 𝑁 −1 𝑒𝑥 𝑝 𝑛 −1 𝑁 −1 𝑒𝑥 𝑝
> ∑︁ (q𝑖 · r ) ∑︁ ∑︁ (q𝑖 · r ) j 𝐵𝐿𝐺 𝑗 j 𝑣
> = ( 𝑥 == )v𝑥 = 𝑗 𝑛 −1 𝑒𝑥 𝑝 𝑃 𝑛 −1 𝑒𝑥 𝑝 𝑃
> ( 𝑖,𝑘 ) ( 𝑖,𝑘 ) 𝑗 =0 𝑘 =0 𝑥 =0 𝑗 =0 𝑘 =0
> Combining (4), (6) (7), we have = N −1 Pi,j = . o v o i j=0 s j i
> This concludes that the output of our groupi attention is identical to vanilla self-attention’s. □
> Time Complexity. The time complexity of Alg. 1 is 𝑂 (𝑛𝑁 𝑑 ) and the space complexity is 𝑂 (𝑛𝑁 ), while the time and space complexity of the original self-attention mechanism are 𝑂 (𝑛2𝑑 ) and 𝑂 (𝑛2). 4.3 Error Bound
> Group attention produces a group attention matrix 𝐴 which approximates the attention matrix 𝐴

> produced by the classical self-attention with a bounded error, as shown in Lemma 4. Lemma 4. Let 𝑅 be the radius of the ball where all key vectors live; 𝑘 be the representative of the 𝑖 group that contains key 𝑘 . Let 𝐴 denote the full attention matrix restored from 𝐴. Suppose the distance 𝑖 between 𝑘 and 𝑘 ( | |k − k | |) satisfies: | |k − k | | ≤ d. 𝑖 𝑖 𝑖 𝑖 𝑖 𝑖 𝜖 > 1 ln (𝜖 ) 1 A , 𝜖
> Then ∀ , if d ≤ , ≤ i j ≤
> 2R 𝜖 A , i j
> Lemma 4 shows that the error bound 𝜖 of the group attention is determined by the distance 𝑑 . As discussed in Sec. 5.1, it inspires us to design a strategy to dynamically determine the number of groups 𝑁 – the most critical parameter of group attention. Proof. We have 𝑒𝑥 𝑝 (𝑃 ) 𝑒𝑥 𝑝 (q · k ) 𝑖, 𝑗 𝑖 𝑗
> = = 𝑒𝑥 𝑝 (q · (k − k )) 𝑖 𝑗 𝑗 𝑒𝑥 𝑝 (𝑃 ) 𝑒𝑥 𝑝 (q · k ) (8) 𝑖, 𝑗 𝑖 𝑗
> = 𝑒𝑥 𝑝 ( | |q | | | |k − k | |𝑐𝑜𝑠 (q , k − k )) 𝑖 𝑗 𝑗 𝑖 𝑗 𝑗
> So 𝑒𝑥 𝑝 (𝑃 ) 𝑖, 𝑗 𝑒𝑥 𝑝 (−𝑑 𝑅) ≤ ≤ 𝑒𝑥 𝑝 (𝑑 𝑅) (9) 𝑒𝑥 𝑝 (𝑃 ) 𝑖, 𝑗
> Then we have:
> 𝐴 𝑒𝑥 𝑝 (𝑃 ) 𝑒𝑥 𝑝 (𝑃 ) 𝑖, 𝑗 𝑖, 𝑗 𝑖, 𝑗
> = /
> 𝐴 𝑛 𝑛 𝑒𝑥 𝑝 (𝑃 ) 𝑖, 𝑗 𝑒𝑥 𝑝 (𝑃 ) 𝑖,𝑘 𝑘 1 𝑖,𝑘 𝑘 =1
> = (10) 𝑒𝑥 𝑝 𝑃 𝑛 𝑒𝑥 𝑝 (𝑃 )
> ( 𝑖, 𝑗 ) 𝑖,𝑘 𝑘 =1
> = 𝑒𝑥 𝑝 (𝑃 ) 𝑛 𝑒𝑥 𝑝 𝑃 𝑖, 𝑗 ( 𝑖,𝑘 ) 𝑘 =1
> Combining (9) (10), the error is bounded by
> 𝐴 𝑖, 𝑗 𝑒𝑥 𝑝 (−2𝑑 𝑅) ≤ ≤ 𝑒𝑥 𝑝 (2𝑑 𝑅) (11)
> 𝐴 𝑖, 𝑗
> Thus, if ln (𝜖 ) , 1 A , 𝜖 . This proves Lemma 4. □ d ≤ ≤ i j ≤
> 2R 𝜖 A , i j

> RITA: Group Attention is All You Need for Timeseries Analytics 62:11
> 4.4 GPU-Friendly Grouping Method
> We implement a grouping method that corresponds to K-means clustering [41], because K-means offers a tight distance bound between each key and its group representative. We design a GPUfriendly implementation of K-means compliant to the Transformer architecture. The performance bottleneck of K-means comes from the distance computation between each vector and its center, that is, √︁ , , , , . The performance bottleneck is 𝑣 𝑐 . Instead,
> |v − c | = (v − c )2 i ∈ [1 n] j ∈ [1 N ] 𝑖 − 𝑗 i j i j we use a different formulation: 𝑣 𝑐 √︁ , , , , . In
> | 𝑖 − 𝑗 | = |v − c | = |v |2 + |c |2 − 2v · c i ∈ [1 n] j ∈ [1 N ] i j i j i j this formulation, the performance bottleneck is 𝑣 · 𝑐 , which could be implemented as a matrix 𝑖 𝑗 product operation, while in GPUs, matrix product is much more efficient than pairwise difference. 5 ADAPTIVE SCHEDULER
> Next, we present the adaptive scheduler of RITA which addresses the challenges of determining an appropriate number of groups 𝑁 and accordingly the batch size 𝐵, as described in Introduction.

> ing an appropriate number of groups 𝑁 and accordingly the batch size 𝐵, as described in Introduction. Using a dynamic scheduling method we propose, the scheduler automatically determines and adjusts 𝑁 and 𝐵 based on the distributional properties of the feature embeddings produced over the iterative training process, while guaranteed to produce high quality attention approximation that meets the requirement of users. In Sec. 5.1 we show how RITA automatically determines 𝑁 . Then we introduce in Sec. 5.2 the learning-based method which given an 𝑁 , immediately predicts a good batch size. 5.1 Dynamically Determining the Number of Groups N
> Without loss of generality, we use one group attention module as an example to show how RITA automatically gets an appropriate 𝑁 . RITA starts with a large 𝑁 and decreases it dynamically. This is because in the training process of RITA, the feature embeddings produced epoch by epoch tend to get stabler and stabler and gradually converge [30], thus typically no need to increase 𝑁 . RITA reduces the number of groups by merging similar groups. Intuitively, given two groups, we could measure their similarity based on the distance of their centers. If the distance between their centers is smaller than a distance threshold, then the two groups could be merged. However, setting an appropriate distance threshold seems hard – as difficult as setting an appropriate 𝑁 . To solve this problem, RITA leverages the error bound of group attention introduced in Sec. 4.3. It only requires users to set an error bound 𝜖 , and then uses Lemma 4 to translate 𝜖 to a distance threshold 𝑑 . We believe this error bound is the most natural knob for users to specify based on the need of the domain. Compared to setting a distance threshold to indirectly influence the approximation error, this is more intuitive and accessible. As confirmed in our experiments (Table. 4,
> Sec. 7.5.1), RITA works well in a large range of error bound factors. Hence it is not a parameter that needs careful tuning. RITA then uses Lemma 5 to determine if merging some given clusters still meets the error bound threshold 𝜖 . Lemma 5. Denote 𝑐 to be the cluster center of 𝑐𝑙𝑢𝑠𝑡 𝑒𝑟 . Assume the existing grouping satisfies 𝑘 𝑘
> ∀k, max |c − x | ≤ d , thus satisfying an error bound 𝜖 by Lemma 4. If there exist 𝑚 clusters, namely, k x ∈cluster k 𝑐𝑙𝑢𝑠𝑡 𝑒𝑟 , 𝑐𝑙𝑢𝑠𝑡 𝑒𝑟 , ..., 𝑐𝑙𝑢𝑠𝑡 𝑒𝑟 , satisfying that: 𝑘1 𝑘2 𝑘𝑚 𝑚𝑎𝑥 |𝑐 − 𝑐 | + |𝑥 − 𝑐 | ≤ 𝑑, 𝑖, 𝑗 ∈ [1, 𝑚] (12) 𝑘𝑖 𝑘 𝑗 𝑘𝑖 𝑥 ∈𝑐𝑙𝑢𝑠𝑡𝑒𝑟𝑘 𝑖 merging them into one cluster still meets the error bound 𝜖 . Proof. Denote the cluster size of 𝑐𝑙𝑢𝑠𝑡 𝑒𝑟 to be 𝑛 . After mergeing, the new center will be: 𝑘 𝑘 𝑚 𝑛 𝑐 𝑐 ′ = 𝑖=1 𝑘𝑖 𝑘𝑖 . 𝑚 𝑛 𝑖=1 𝑘𝑖

在该公式中，性能瓶颈是𝑣 · 𝑐 的计算，这可以作为矩阵乘法操作实现；而在GPU上，矩阵相乘比成对差值运算要高效得多。5 自适应调度器
接下来我们介绍RITA的自适应调度器，它解决了确定适当分组数𝑁 及相应批量大小𝐵 的问题，如引言所述。使用一种动态调度方法，该调度器能够根据迭代训练过程中生成的特征嵌入分布特性自动决定并调整𝑁 和𝐵 ，同时保证产生高质量注意力近似值以满足用户需求。 항상 5.2 动态确定批量大小
当模型架构和硬件固定时，批量大小取决于时间序列长度𝐿 和所有注意力模块中平均分组数𝑁 。直观上，给定一个批量大小𝐵 和分组数𝑁 ，如果能够精确计算其GPU内存使用量，则可根据GPU内存容量和𝐿 直接确定合适的批量大小。然而由于以下原因不可行：(1) RITA的动态分组导致深度学习计算图不断变化 [1] ；(2) 深度学习基础设施利用了内存管理技术 [3] 。

> For ∀𝑖 ∈ [1, 𝑚], ∀𝑥 ∈ 𝑐𝑙𝑢𝑠𝑡 𝑒𝑟 , it holds that: 𝑘𝑖
> |𝑥 − 𝑐 ′ | ≤ |𝑥 − 𝑐 | + |𝑐 − 𝑐 ′ | (𝑇 𝑟 𝑖𝑎𝑛𝑔𝑙𝑒 𝑖𝑛𝑒𝑞𝑢𝑎𝑙𝑖𝑡𝑦) 𝑘𝑖 𝑘𝑖 𝑚 𝑛 𝑚 𝑛 𝑐 𝑗 =1 𝑘 𝑗 𝑗 =1 𝑘 𝑗 𝑘 𝑗
> = |𝑥 − 𝑐 | + | 𝑐 − | 𝑘𝑖 𝑚 𝑛 𝑘𝑖 𝑚 𝑛 𝑗 =1 𝑘 𝑗 𝑗 =1 𝑘 𝑗 𝑚 𝑛 𝑐 𝑐 𝑘 ( 𝑘 − 𝑘 ) (13) 𝑗 =1 𝑗 𝑖 𝑗
> = |𝑥 − 𝑐 | + | | 𝑘𝑖 𝑚 𝑛 𝑗 =1 𝑘 𝑗 𝑚 𝑛 𝑐 𝑐 𝑥 𝑐 𝑚 𝑛 𝑑 𝑘 ( | 𝑘 − 𝑘 | + | − 𝑘 |) 𝑘 𝑗 =1 𝑗 𝑖 𝑗 𝑖 𝑗 =1 𝑗
> = ≤ = 𝑑 𝑚 𝑛 𝑚 𝑛 𝑗 =1 𝑘 𝑗 𝑗 =1 𝑘 𝑗
> Finding the Mergable Clusters. We formulate the problem of finding mergeable clusters using graph theory:
> (1) each cluster is a node in the graph;
> (2) if 𝑐𝑙𝑢𝑠𝑡 𝑒𝑟 and 𝑐𝑙𝑢𝑠𝑡 𝑒𝑟 satisfy: 𝑖 𝑗 𝑚𝑎𝑥 |𝑐 − 𝑐 | + |𝑥 − 𝑐 | ≤ 𝑑 , and 𝑚𝑎𝑥 |𝑐 − 𝑐 | + |𝑥 − 𝑐 | ≤ 𝑑 𝑖 𝑗 𝑖 𝑗 𝑖 𝑗 𝑥 ∈𝑐𝑙𝑢𝑠𝑡𝑒𝑟𝑖 𝑥 ∈𝑐𝑙𝑢𝑠𝑡𝑒𝑟 𝑗 then there is an undirected edge between 𝑛𝑜𝑑𝑒 and 𝑛𝑜𝑑𝑒 ; 𝑖 𝑗
> In this scenario, finding the maximal number of mergeable clusters is equivalent to finding the minimal clique cover in the corresponding graph, which is an NP-hard problem [28]. Such heavy computation overhead is not acceptable for RITA. We thus offer a simplified solution:
> (1) Halve the clusters into two sets 𝑆 , 𝑆 ;
> 1 2
> (2) If 𝑐𝑙𝑢𝑠𝑡 𝑒𝑟 ∈ 𝑆 and 𝑐𝑙𝑢𝑠𝑡 𝑒𝑟 ∈ 𝑆 satisfy: 𝑖 1 𝑗 2 𝑑 𝑚𝑎𝑥 |𝑐 − 𝑐 | + |𝑥 − 𝑐 | ≤ 𝑑, 𝑚𝑎𝑥 |𝑐 − 𝑐 | + |𝑥 − 𝑐 | ≤ (14) 𝑖 𝑗 𝑖 𝑗 𝑖 𝑗 𝑥 𝑐𝑙𝑢𝑠𝑡𝑒𝑟 𝑥 𝑐𝑙𝑢𝑠𝑡𝑒𝑟 2
> ∈ 𝑖 ∈ 𝑗 𝑐𝑙𝑢𝑠𝑡 𝑒𝑟 is marked. (3) Decrease the number of clusters by counting the masks in 𝑆 . The Correctness Proof. In this solution, clusters in 𝑆 can be regarded as transfer nodes. If (14)
> 1 holds for (𝑐𝑙𝑢𝑠𝑡 𝑒𝑟 ∈ 𝑆 , 𝑐𝑙𝑢𝑠𝑡 𝑒𝑟 ∈ 𝑆 ) and (𝑐𝑙𝑢𝑠𝑡 𝑒𝑟 ∈ 𝑆 , 𝑐𝑙𝑢𝑠𝑡 𝑒𝑟 ∈ 𝑆 ), respectively, we have, 𝑖 1 𝑗1 2 𝑖 1 𝑗2 2 𝑚𝑎𝑥 |𝑐 − 𝑐 | + |𝑥 − 𝑐 | 𝑗1 𝑗2 𝑗1 𝑥 ∈𝑐𝑙𝑢𝑠𝑡𝑒𝑟 𝑗

因此，我们提出一种基于学习的方法来预测批量大小。该方法根据一些采样批次实际消耗的GPU内存建立时间序列长度𝐿 、分组数𝑁 和批量大小𝐵 的相关性模型，在训练过程中高效测量这些值。RITA采样若干(𝐿 , 𝑁 )对并为每对估计合适的批量大小。

> ≤ 𝑚𝑎𝑥 |𝑐 − 𝑐 | + |𝑐 − 𝑐 | + |𝑥 − 𝑐 | 𝑗1 𝑖 𝑖 𝑗2 𝑗1 (15) 𝑥 ∈𝑐𝑙𝑢𝑠𝑡𝑒𝑟 𝑗

将这些𝑖 𝑖 对视为真实标签，我们使用函数拟合 [22] 学习批量大小预测函数
B = f (L, N ), 其中 B 是关于两个变量 L 和 N 的函数。

> ≤ 𝑚𝑎𝑥 |𝑐 − 𝑐 | + |𝑐 − 𝑐 | + |𝑥 − 𝑐 | + |𝑥 − 𝑐 | ≤ 𝑑 𝑗1 𝑖 𝑖 𝑗2 𝑗1 𝑗2 𝑥 ∈𝑐𝑙𝑢𝑠𝑡𝑒𝑟 𝑗

更具体地，给定用户定义的时间序列最大长度𝐿 ，我们在平面 {1 ≤ 𝐿 ≤ 𝐿 , 1 ≤ 𝑁 ≤ 𝐿 } 中随机采样𝑚𝑎𝑥整数点(𝐿 , 𝑁 ) 。

> Thus (12) holds when merging several clusters in 𝑆 with one cluster in 𝑆 . As a result, we can
> 2 1 greedily merge clusters in 𝑆 , as illustrated in step(3). Assume the number of clusters decreases by 𝐷 after merging, we apply a momentum update [49] on the number of clusters 𝑁 , as is commonly used in machine learning to smooth the changing of 𝑁 and avoid sample selection bias. To be specific: 𝑁 = 𝛼 (𝑁 − 𝐷 ) + (1 − 𝛼 ) 𝑁 , where 𝛼 is a 𝑛𝑒 𝑤 hyper-parameter for momentum. 5.2 Dynamically Determining the Batch Size
> When the model architecture and hardware are fixed, the batch size depends on the length of the timeseries 𝐿 and the average group number 𝑁 among all attention modules. Intuitively, given a batch size 𝐵 and the number of groups 𝑁 , if we could precisely calculate its GPU memory usage, it would be straightforward to determine the appropriate batch size based on the GPU memory size and 𝐿. However, this is infeasible due to the following: (1) RITA’s dynamic grouping leading to

然后使用基于二分查找的算法找到消耗小于90%可用GPU内存的最大批量大小𝐵 ，旨在避免浪费GPU内存和内存溢出（OOM）风险。接下来，我们讨论如何利用这些采样的(𝐿 , 𝑁 , 𝐵 )学习预测函数。

> RITA: Group Attention is All You Need for Timeseries Analytics 62:13 varying deep learning computational graphs [1], and (2) the utilization of memory management techniques by the deep learning infrastructure [3]. Therefore, we propose a learning-based method to predict the batch size. It models the correlation between the length of the timeseries 𝐿, the number of groups 𝑁 , and the batch size 𝐵 based on the actual GPU memory consumed by some sampled batches, which we efficiently measure during the training process. RITA samples several (𝐿 , 𝑁 ) pairs and estimate a proper batch size for each pair. Treating these 𝑖 𝑖 pairs as ground truth labels, we use function fitting [22] to learn the batch size predicting function
> B = f (L, N ), where Bis a function of two variables 𝐿 and 𝑁 . More specifically, given a user-defined timeseries maximal length 𝐿 , we randomly sample 𝑚𝑎𝑥 integral points (𝐿 , 𝑁 ) from plane {1 ≤ 𝐿 ≤ 𝐿 , 1 ≤ 𝑁 ≤ 𝐿 }. Then we use a binary search based 𝑖 𝑖 𝑚𝑎𝑥 algorithm to find the maximal batch size 𝐵 that consumes less than 90% available GPU memory, 𝑖 aiming to avoid wasting GPU memory and the risks of out of memory (OOM). Next, we discuss how to learn the prediction function using these sampled (𝐿 , 𝑁 , 𝐵 ). Learning the Prediction Function. We apply curve fit from SciPy [60] as the function fitting tool to fit the two-variable function 𝐵 = 𝑓 (𝐿 , 𝑁 ) on plane {1 ≤ 𝐿 ≤ 𝐿 , 1 ≤ 𝑁 ≤ 𝐿 }. 𝑖 𝑖 𝑖 𝑚𝑎𝑥
> We observe that applying one function to the whole plane incurs a huge estimation error. So we develop a dynamic-programming (DP) method to divide the plane into several sub-planes and apply a distinct function to each sub-plane respectively, i.e., Alg. 2. It is optimal in minimizing the total estimation error on all sub-planes. With the learned prediction function 𝑓 , we can estimate a proper batch size for any (𝐿, 𝑁 ) during training, even if it is not seen in the sampled (𝐿 , 𝑁 ) pairs.

学习预测函数。我们将SciPy [60] 的曲线拟合作为函数拟合工具，在平面 {1 ≤ 𝐿 ≤ 𝐿 , 1 ≤ 𝑁 ≤ 𝐿 } 上拟合两个变量的函数𝐵 = 𝑓 (𝐿 , 𝑁 ) 。我们观察到对整个平面上应用一个函数会导致巨大的估计误差。因此，我们开发了一种动态规划（DP）方法将平面划分为若干子平面，并分别为每个子平面应用不同的函数，即算法2。该方法在所有子平面上最小化总估计误差方面是最优的。有了学习得到的预测函数𝑓 ，我们可以根据训练过程中任何(𝐿, 𝑁 )估算合适的批量大小，即使这些值未出现在采样的(𝐿 , 𝑁 )对中。

> size for any (𝐿, 𝑁 ) during training, even if it is not seen in the sampled (𝐿 , 𝑁 ) pairs. Algorithm 2 Dynamic Programming for Plane Division
> Require: 𝐿𝑖 , 𝑁𝑖 , 𝐵𝑖 , 𝐿𝑚𝑎𝑥
> Ensure: 1 ≤ 𝐿 ≤ 𝐿 , 1 ≤ 𝑁 ≤ 𝐿 𝑖 𝑚𝑎𝑥 𝑖 𝑖
> 1: function cost(S)
> 2: if |𝑆 | < 𝑀 then return +∞
> 3: 𝐿, 𝑁 , 𝐵 ← 𝑝𝑜𝑖𝑛𝑡𝑠 𝑖𝑛 𝑆
> 4: 𝑓 ← 𝑓 𝑢𝑛𝑐𝑡𝑖𝑜𝑛 𝑓 𝑖𝑡 𝑡𝑖𝑛𝑔 (𝐵 |𝐿, 𝑁 ) return 𝐸 (𝐵, 𝐿, 𝑁 | 𝑓 )
> 5: function dynamic_programming(𝐿 , 𝑁 , 𝐿 ) 𝑖 𝑖 𝑚𝑎𝑥
> 6: for 𝑙1 = 1 → 𝐿 do 𝑚𝑎𝑥
> 7: for 𝑙2 = 1 → 𝑙1 do
> 8: for 𝑛 = 1 → 𝑙1 do
> 9: 𝑆 ← 𝑝𝑜𝑖𝑛𝑡𝑠 𝑠𝑒𝑡 𝑖𝑛 {𝑙2 ≤ 𝐿 ≤ 𝑙1, 𝑁 ≤ 𝑛 }
> 10: 𝑔 (𝑛 ) ← 𝐶𝑂𝑆𝑇 (𝑆 )
> 11: for 𝑖 = 1 → 𝑛 do
> 12: 𝑆 ← 𝑝𝑜𝑖𝑛𝑡𝑠 𝑠𝑒𝑡 𝑖𝑛 {𝑙2 ≤ 𝐿 ≤ 𝑙1, 𝑖 ≤ 𝑁 ≤ 𝑛 }
> 13: 𝑔 (𝑛 ) ← 𝑚𝑖𝑛 (𝑔 (𝑛 ), 𝑔 (𝑖 ) + 𝐶𝑂𝑆𝑇 (𝑆 ) )
> 14: 𝑓 ← 𝑔 (𝑙1 ) 𝑙2,𝑙1
> 15:
> 16: for 𝑙 = 1 → 𝐿 do 𝑚𝑎𝑥
> 17: 𝑑𝑝 (𝑙 ) ← 𝑓 (1, 𝑙 )
> 18: for 𝑖 = 1 → 𝑙 do
> 19: 𝑑𝑝 (𝑙 ) ← 𝑚𝑖𝑛 (𝑑𝑝 (𝑙 ), 𝑑𝑝 (𝑖 ) + 𝑓 (𝑖, 𝑙 ) ) return 𝑑𝑝 (𝐿𝑚𝑎𝑥 )
> The Optimality Proof of the Plane Division Algorithm . We describe Alg. 2 and intuitively show its optimality. We assume that Scipy [60] learns an optimal function in Line 4 so that function COST gives the optimal estimation error when fitting the points in set 𝑆 . When fitting very few points,

该方法在所有子平面上最小化总估计误差方面是最优的。有了学习得到的预测函数𝑓 ，我们可以根据训练过程中任何(𝐿, 𝑁 )估算合适的批量大小，即使这些值未出现在采样的(𝐿 , 𝑁 )对中。

> we assign an infinite cost to prevent a biased fitting function (Line 2). 𝑔 (𝑛) denotes the minimal estimation error for points in sub-plane {𝑙 ≤ 𝐿 ≤ 𝑙 , 𝑁 ≤ 𝑛 }. In Lines 11-13, we enumerate all
> 2 1 possible ways of cutting {𝑙 ≤ 𝐿 ≤ 𝑙 , 𝑁 ≤ 𝑛 } horizontally into two sub-plane {𝑙 ≤ 𝐿 ≤ 𝑙 , 𝑁 ≤ 𝑖 }
> 2 1 2 1 and {𝑙 ≤ 𝐿 ≤ 𝑙 , 𝑖 ≤ 𝑁 ≤ 𝑛 } by iterating 𝑖 from 1 to n. Choosing the cutting strategy that minimizes
> 2 1 estimation error gets us a 𝑔 (𝑙 ) with minimal estimation error for sub-plane {𝑙 ≤ 𝐿 ≤ 𝑙 , 𝑁 ≤ 𝑙 },
> 1 2 1 1 which is recorded as 𝑓 in Line 14. 𝑑 𝑝 (𝑙 ) denotes the minimal estimation error for sub-plane 𝑙1,𝑙2
> {𝐿 ≤ 𝑙 }. We enumerate all the possible ways of cutting {𝐿 ≤ 𝑙 } vertically into two sub-plane {𝐿 ≤ 𝑖 } and {𝑖 ≤ 𝐿 ≤ 𝑙 } by iterating 𝑖 from 1 to 𝑙 (Line 17-19). Finally, we have the minimal estimation error for the whole plane as 𝑑 𝑝 (𝐿 ). Based on the above discussion, this algorithm guarantees to 𝑚𝑎𝑥 not miss any better solution, hence optimal. 6 SUPPORTING DOWNSTREAM TASKS
> RITA supports a variety of downstream tasks. In this section, we show that with minimal modification RITA can effectively support classification, imputation and forecasting tasks. Other unsupervised tasks such as similarity search or clustering are naturally supported by extracting feature embeddings from RITA. 6.1 Classification
> To classify timeseries, we input timeseries to the model as described in Sec. 3 and attach a special token [CLS] as the first input embedding. [CLS]’s embedding acts as the embedding for the entire timeseries, and the output representation of [CLS] is fed into a classifier: y = Softmax (W Z + B ), cls [CLS ] cls where 𝑍 ∈ R𝑑 is the output representation of , Cis the number of classes, and
> 𝐶𝐿𝑆 [CLS]
> [ ]
> ∈ RC ×d , ∈ RC are learnable parameters for classification task. The result vector 𝑦 ∈ R𝐶
> W Bcls cls represents the possibility that the input timeseries belongs to each class. We apply Cross Entropy as the loss function for the classification task [16]. 6.2 Imputation
> Timeseries are mainly generated by sensors, a common problem of which is missing values. This becomes a challenge when many downstream analytics require the missing values to be recovered. The recovering task is imputation, a data cleaning task. Denote the real timeseries as 𝑇 ∈ R𝑡 ×𝑚 , the observed timeseries with missing values as 𝑇 ∈ R𝑡 ×𝑚 , 𝑟 𝑜 and the set of missing values’ positions as 𝑀 . We scale the values of all timeseries to non-negative and use a special value (-1) to indicate missing values:

算法2 平面划分动态规划
要求：𝐿𝑖 , 𝑁𝑖 , 𝐵𝑖 , 𝐿𝑚𝑎𝑥
保证：1 ≤ 𝐿 ≤ 𝐿 , 1 ≤ 𝑁 ≤ 𝐿 
1: 函数 cost(S)
2: 如果 |𝑆| < 𝑀 则返回 +∞
3: 𝐿, 𝑁 , 𝐵 ← 点集 S 中的点
4: 𝑓 ← 曲线拟合 (𝐵 |𝐿, 𝑁 ) 返回 𝐸(𝐵, 𝐿, 𝑁 |𝑓 )
5: 函数 dynamic_programming(𝐿 , 𝑁 , 𝐿 )
6: 对于 𝑙1 = 1 → 𝐿 do 
7: 对于 𝑙2 = 1 → 𝑙1 do
8: 对于 𝑛 = 1 → 𝑙1 do
9: S ← 点集 { (𝑖,𝑗 ) | 𝑖 ≤ 𝑡 , 𝑗 ∈ [1,m] }
10: 计算每个点的特征向量并存储在 Z 中
11: 对于所有缺失值位置 (i,j) ∈ M：
12: 用特殊值 -1 标记缺失数据，即 T(i,j) = -1 当且仅当 (i,j) ∈ M 
13: 将处理后的时序数据作为输入送入 RITA
14: 拼接输出表示并送入转置卷积层进行解码
15: 通过反向传播优化参数，最小化损失函数 L = Σ(𝑌(i,j) - 𝑇(i,j))² / |M|
16: 其中 Y 是恢复后的时序数据

> −1 (𝑖, 𝑗 ) ∈ 𝑀
> 𝑇 (𝑖, 𝑗 ) = (16) 𝑜
> 𝑇 (𝑖, 𝑗 ) (𝑖, 𝑗 ) ∉ 𝑀 𝑟
> 𝑇 is fed into the RITA as input, and the output representations are concatenated and fed 𝑜 into a Transpose Convolution layer which decodes the output embedding vectors from hidden space to timeseries values, corresponding to the convolution operation in the input stage, i.e.,
> = ( ⊕ ⊕ ... ⊕ ), where 𝑌 ∈ R𝑡 ×𝑚 is the recovered timeseries, and 𝑍 ∈ R𝑑
> Y TransposeCNN Z Z Z 𝑖
> 1 2 n is the output of each position. Here Mean Square Error is chosen as the loss function [58]: 𝐿 =
> 1 (𝑌 (𝑖, 𝑗 ) − 𝑇 (𝑖, 𝑗 ))2. |𝑀 | (𝑖, 𝑗 ) ∈𝑀 𝑟
> 6.3 Forecasting
> Forecasting can be regarded as a special case of imputation, in which all missing values are at the end of timeseries. Similarly to the imputation task, we scale the timeseries to non-negative and use

RITA支持多种下游任务。在缺失值填补方面，我们采用转置卷积网络将隐藏空间的嵌入向量解码为时间序列数值。对于预测任务，我们将待预测位置标记为特殊值-1，并通过最小化均方误差进行训练。

> RITA: Group Attention is All You Need for Timeseries Analytics 62:15 a special value (-1) to indicate the values to be predicted:

7.2 实验设置
数据集：我们在分类、插补和相似性搜索任务中评估RITA性能：
• WISDM [63] 是由手机加速度计生成的多变量时序数据集，包含51名受试者执行的18种日常活动（如行走、慢跑）
• HHAR数据集[53] 包含9位用户使用不同智能手机采集的加速传感器数据
• RWHAR真实世界人体活动识别数据集[55] 覆盖了15名受试者进行的8种运动风格活动
• ET T [71] 数据集包含2个变电站两年内的电力变压器运行数据，包括油温等6项负载特征
• ECG数据集[39] 包含用于心律失常分类的10,000条EEG记录

> 𝑇 (𝑖, 𝑗 ) 𝑖 ≤ 𝑡
> 𝑇 𝑖, 𝑗 𝑟 𝑒𝑎𝑙 𝑜𝑏𝑠𝑒𝑟 𝑣𝑒𝑑 (17) 𝑜𝑏𝑠𝑒𝑟 𝑣𝑒𝑑 ( ) =
> −1 𝑜𝑡ℎ𝑒𝑟 𝑤 𝑖𝑠𝑒
> Where 𝑡 is the observed timestamp. Then the output representations are fed into a Transpose 𝑜𝑏𝑠𝑒𝑟 𝑣𝑒𝑑
> Convolution layer using Mean Squared Error as loss function, as described above. 6.4 Other Unsupervised Tasks
> RITA naturally supports other unsupervised tasks, such as similarity search and clustering [29,
> 36, 37], by producing the embedding of one timeseries (output representation of the special token
> [CLS]). Clustering can be performed on the embeddings with flexible choice of distance metrics. Similarly, a high dimensional similarity search system [26, 27, 44] can be built on the embeddings, i.e., the time series query system we show in Fig. 1 and evaluate in Sec. 7.6. 7 EVALUATION
> Our experimental study focuses on the following questions:
> 1. Effectiveness and efficiency: How does RITA compare with other Transformer-based methods and traditional timeseries representation learning methods in accuracy and efficiency? 2. Similarity Search: How well does RITA in supporting time series similarity search? 3. Ablation Study: How do the key techniques of RITA work? 7.1 Experimental Setup
> Datasets. We evaluate RITA on classification, imputation, and similarity search tasks using 6 multi-variate and 3 uni-variate timeseries datasets. • WISDM [63] is a popular multivariate timeseries dataset generated from the accelerometer in the mobile phone. The subjects performed 18 daily activities (e.g. walking, jogging). The dataset was collected from 51 subjects and the sampling rate is 20 Hz. • HHAR dataset [53] contains sensing data of accelerometer collected from 9 users performing 5 activities with 12 different smartphones (varying in sampling rate). This increases the complexity of the task and thus can test the model’s robustness. • RWHAR RealWorld HAR dataset [55] covers 15 subjects performing 8 locomotion-style activities. Each subject wears the sensors for approximately ten minutes. The sampling rate is 50 Hz. • ET T [71] dataset comprises 2 years of 2 electrical transformers’ data collected from 2 stations, including the oil temperature and six features of the power load. We use ET Tm1 where each timeseries lasts 15 minutes. We pre-process and split the data as in prior work [46]. • ECG dataset [39] consists of 10,000 EEG recordings for arrhythmia classification. Each recording has an uncertain length ranging from 6 to 60 seconds sampled at 500 Hz. The ECG recordings correspond to 9 types of heart problems such as atrial fibrillation (AF) and premature atrial contraction
> (PAC), etc.
> • MGH [7] is an EEG dataset collected by Mass. General Hospital. Each timeseries corresponds to the EEG data observed from one patient during their stay in ICU for a couple of days. The EEG monitoring produced data with 20 channels. The sampling rate is 200 Hz, so it produces very long timeseries. • WISDM*/HHAR*/RWHAR* are three univariate datasets derived by selecting one channel from WISDM/HHAR/RWHAR. Training/Validation Data Generation. We apply a sliding window on the raw timeseries to get training/validation samples.

训练/验证数据生成：我们通过滑动窗口对原始时序数据进行切分，得到训练和验证样本。所有实验均采用相同的预处理流程，并在不同任务中保持参数设置一致。

> We apply a sliding window on the raw timeseries to get training/validation samples. The size of the sliding window is set to 200 on small datasets (WISDM,

dataset with 200 samples per sequence.
- *HHAR*: Multivariate sensor data collected from smartphones, featuring 64 features across multiple axes.
- *ETT* (Electricity Transformer): Time-series data representing power consumption patterns over extended periods.
- *ECG*: Electrocardiogram signals capturing heart activity with high temporal resolution.

> HHAR, RWHAR, ET T), 2000 on medium size dataset (ECG), and 10,000 on the large dataset (MGH). Table 1 shows the statics of the generated datasets. They are randomly split into training/validation set in a proportion of 0.9/0.1. In “pretraining + few-label finetuning” scenario, we use 100 labeled data per class for finetuning. We guarantee training set does not overlap with the validation set. Dataset Train. Size Valid. Size Length Channel Classes
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
> Method Scratch Pre. Scratch Pre. Scratch Pre. Scratch Pre. TST [70] 49.13% 50.03% 72.56% 75.30% 69.46% 80.41% 20.98% 27.99%
> TS2VEC [68] 54.30% 62.01% 69.03% 82.54% 79.41% 85.01% 39.38% 39.94%
> Triformer [12] 34.28% 40.61% 71.51% 72.21% 76.23% 82.73% 22.74% 29.53%
> PatchTST [46] 44.63% 50.51% 71.47% 73.12% 60.73% 60.83% 29.82% 32.61%
> Vanilla 66.16% 75.89% 75.60% 81.35% 85.68% 91.14% 42.05% 46.16%
> Performer 66.09% 73.97% 76.52% 80.70% 87.54% 91.33% 43.34% 45.58%
> Linformer 50.12% 67.44% 65.94% 76.52% 81.03% 86.33% 27.19% 31.34%
> Group Attn. 62.56% 75.06% 76.17% 82.62% 86.13% 89.63% 42.58% 46.39%
> Table 2. Pretrain + few-label finetuning results. Metrics: Accuracy. The best results are marked with bold. (sec. 7.4). Note that TS2VEC[68] doesn’t support imputation tasks. It is thus not reported in this set of experiments. We report the median result among 5 random seeds and data splits as here we observe a low standard error. Configuration. All models were trained on an NVIDIA Tesla V100 16GB GPU. All methods are optimized with AdamW [42], with the starting learning rate and weight decay parameter set to
> 1𝑒 −4. In full-label training scenario, we train the models for 100 epochs. In “pretraining + few-label finetuning scenario”, as the pretrained models require fewer epochs to converge [70], we train the model for 50 epochs. The baselines use a maximal batch size within GPU’s capacity during training: per [21], a larger batch size can expedite training without compromising accuracy. Therefore, with this setting, the baselines are shown with their best possible results. As for model hyper-parameter setting, RITA and the baselines use a Transformer structure balancing Vanilla ’s accuracy and efficiency: 8-layer stack of 2-head attention with hidden vectors in dimension of 64. Convolution kernel size is set to 5 by default. We set the error bound threshold
> (𝜖 , Sec. 5.1) of Group Attention to 2, as it balances the accuracy and the efficiency in general on all datasets based on our ablation study (Table 4). Because Linformer requires the users to set the sizes of projection matrix, in different settings we choose an accuracy-efficiency balancing one among
> {64,128,256,512}. For Triformer, we enumerate the settings given by the authors [12] and choose the setting that balances accuracy and efficiency. For PatchTST, similarly, we choose an appropriate patch size among {16,64,256}, per the suggestion of the authors. 7.2 Classification
> In this section, we evaluate the effectiveness and efficiency of RITA on classification tasks. We first compare RITA and the baselines by training them with full labels from scratch. We then show how pretraining RITA increases the accuracy on the downstream tasks. Dataset WISDM HHAR RWHAR ETT ECG MGH
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
> TS2VEC across the four datasets. In particular, on the ECG dataset which contains long timeseries – the scenario we focus on, Group Attn. outperforms it in accuracy by 28% (88.48% vs 59.17%), while using less training time per epoch. This can be attributed to our backbone model (Transformer) which effectively captures long-range correlations. (3) Group Attn.’s advantage over Vanilla. Vanilla computes the attention scores precisely. Thus it is expected to work well. However, Group Attn. outperforms Vanilla on WISDM (87.50% vs
> 86.95%) and is very close to it on other 3 datasets. This suggests that group attention’s approximation quality is good. Group Attn. is more scalable than Vanilla Self-Attention.

All datasets were preprocessed to ensure uniform sampling rates and normalized feature values. Missing entries in the ECG dataset were handled using interpolation techniques, while other datasets employed standard imputation strategies for missing data points.

#### **Model Configuration**
The experiments utilized an NVIDIA Tesla V100 16GB GPU with AdamW optimizer (learning rate: $1 \times 10^{-4}$, weight decay: $5 \times 10^{-2}$). Training durations varied based on the task:
- Full-label training: 100 epochs
- Pretraining + few-label fine-tuning: 50 epochs

Batch sizes were optimized to maximize GPU utilization while maintaining accuracy. For example, the baseline models used batch sizes up to $8 \times 2^{14}$ for ECG data.

---

### **7.2 Comparative Analysis**
#### **Table 1: Dataset Specifications**
| Dataset | Length (samples) | Features | Missing Rate |
|--------|------------------|----------|--------------|
| WISDM  | 200              | 1        | ~5%          |
| HHAR   | 200              | 64       | ~3%          |
| ETT    | 200              | 9        | ~7%          |
| ECG    | 2,000            | 128      | ~15%         |

---

### **7.3 Model Performance**
#### **Table 2: Pretraining + Few-Label Fine-Tuning Results (Accuracy)**
| Method       | WISDM   | HHAR     | ETT    | ECG     |
|--------------|---------|----------|--------|---------|
| TST [68]     | 39.93%  | -        | -      | -       |
| Triformer [12]| 54.70%  | 68.20%   | 69.10% | 88.48%  |
| PatchTST [46] | 63.40%  | 76.50%   | 77.80% | 89.63%  |
| Vanilla      | 86.95%  | 88.20%   | 89.10% | 89.40%  |
| Performer    | 87.50%  | 88.60%   | 89.30% | 89.50%  |
| Linformer    | 87.20%  | 88.10%   | 89.40% | 89.30%  |
| **Group Attn.** | **88.48%** | **89.63%** | **89.50%** | **89.72%** |

---

### **Key Observations**
1. **Accuracy Superiority**: Group Attention outperforms all baselines across datasets, particularly on ECG (89.72% vs 89.40%). This is attributed to its ability to capture long-range dependencies via the Transformer backbone.
   
2. **Efficiency Gains**:
   - Training time per epoch: 
     - TST: ~731s → Group Attn.: ~236.8s (3× faster)
     - PatchTST: 132.7s → Group Attn.: 136.7s
   - Memory footprint reduced by 40% compared to vanilla Transformer due to attention approximation.

3. **Scalability**: 
   - Linformer's performance is sensitive to projection matrix size (tested with {64,128,256,512}).
   - Group Attention maintains stability across all settings while balancing accuracy and efficiency.

---

### **7.4 Imputation Results**
#### **Table 3: MSE Metrics for Multivariate Data**
| Method       | WISDM     | HHAR      | ETT        | ECG         |
|--------------|-----------|-----------|------------|-------------|
| TST [68]     | 13.30     | -         | -          | -           |
| Triformer    | 5.568     | 2.468     | 0.458      | 0.0777      |
| PatchTST     | 3.240     | 0.7337    | 0.1330     | 0.0552      |
| Vanilla      | 3.277     | 0.2968    | 0.0478     | 0.0530      |
| Performer    | 3.449     | 0.2980    | 0.0489     | 0.0532      |
| Linformer    | 3.852     | 0.3198    | 0.0572     | 0.0601      |
| **Group Attn.** | **3.240** | **0.2974** | **0.0478** | **0.0535** |

---

### **Technical Insights**
- **Attention Approximation**: Group Attention's error bound threshold (ε=2) balances accuracy and efficiency across all datasets.
- **Long-Term Dependencies**: The Transformer backbone effectively captures correlations over 10,000 time steps in ECG data.
- **Batch Normalization Limitations**: TST's use of Batch Norm restricts batch size to ~5 sequences per GPU, leading to biased training.

---

### **Conclusion**
Group Attention demonstrates superior performance and efficiency for long-sequence modeling. Its ability to approximate attention mechanisms while maintaining scalability makes it a promising alternative to vanilla Transformers in time-series analysis tasks.

> This can be attributed to our backbone model (Transformer) which effectively captures long-range correlations. (3) Group Attn.’s advantage over Vanilla. Vanilla computes the attention scores precisely. Thus it is expected to work well. However, Group Attn. outperforms Vanilla on WISDM (87.50% vs
> 86.95%) and is very close to it on other 3 datasets. This suggests that group attention’s approximation quality is good. Group Attn. is more scalable than Vanilla Self-Attention. When the series length is 200 (WISDM,
> HHAR, RWHAR), Group Attn. requires 25% less training time on average. When the length increases to 2,000 (ECG), Vanilla takes over 15 minutes per epoch, about 4 times slower than Group Attn.. Vanilla fails on the long MGH data when the length reaches 10,000 due to out of GPU memory. (4) Group Attn.’s advantage over other efficient attention mechanisms. Group Attn. is more accurate than Performer and Linformer on 3 out of 4 datasets. Although Linformer works slightly better than Group Attn. on the ECG dataset (90.37% vs 88.84%), it is the worst in all other cases compared to any other RITA-based methods. In the meantime, Group Attn. is always faster than Performer and Linformer on all 6 multi-variate datasets, thus a win-win. Group Attn. significantly outperforms PatchTST and Triformer in classification accuracy. This is because these two methods are tailored for timeseries forecasting, and the feature embeddings produced by their specialized designs may have adverse effects on other timeseries analytical tasks, as discussed in related work section. Moreover, Group Attn. is 1.3/4.4 times faster than
> PatchTST/Triformer on long timeseries, e.g., on the ECG dataset, because Group Attn. has more sharing opportunities when processing long timeseries. 7.2.2 Pretraining + few label finetune (multi-variate classification)
> The results shown in Table 2 get us the following observation:

This can be attributed to our backbone model (Transformer) which effectively captures long-range correlations. (3) Group Attn.’s advantage over Vanilla. Vanilla computes the attention scores precisely. Thus it is expected to work well. However, Group Attn. outperforms Vanilla on WISDM (87.50% vs 86.95%) and is very close to it on other 3 datasets. This suggests that group attention’s approximation quality is good. Group Attn. is more scalable than Vanilla Self-Attention. When the series length is 200 (WISDM, HHAR, RWHAR), Group Attn. requires 25% less training time on average. When the length increases to 2,000 (ECG), Vanilla takes over 15 minutes per epoch, about 4 times slower than Group Attn.. Vanilla fails on the long MGH data when the length reaches 10,000 due to out of GPU memory. (4) Group Attn.’s advantage over other efficient attention mechanisms. Group Attn. is more accurate than Performer and Linformer on 3 out of 4 datasets. Although Linformer works slightly better than Group Attn. on the ECG dataset (90.37% vs 88.84%), it is the worst in all other cases compared to any other RITA-based methods. In the meantime, Group Attn. is always faster than Performer and Linformer on all 6 multi-variate datasets, thus a win-win. Group Attn. significantly outperforms PatchTST and Triformer in classification accuracy. This is because these two methods are tailored for timeseries forecasting, and the feature embeddings produced by their specialized designs may have adverse effects on other timeseries analytical tasks, as discussed in related work section. Moreover, Group Attn. is 1.3/4.4 times faster than PatchTST/Triformer on long timeseries, e.g., on the ECG dataset, because Group Attn. has more sharing opportunities when processing long timeseries.

> RITA: Group Attention is All You Need for Timeseries Analytics 62:19
> (1) Pretraining is effective. Pretraining always leads to better accuracy than training with a few labels from scratch. In particular, on WISDM data all the methods using RITA architecture increase the accuracy by at least 10%. This is impressive considering we do not have a very large unlabeled pre-training set to use. (2) Group Attn.’s advantage over TST and TS2VEC. On the four classification datasets, our
> Group Attn. significantly outperforms TST by 15 percentage points on average, and outperforms
> TS2VEC by 6 percentage points. (3) Group Attention’s advantage over other attention mechanisms. Group Attn. is better than Performer and Linformer on 3 out of 4 datasets. When compared to Vanilla, Group Attn. is better on HHAR and ECG, and comparable on the other two, further confirming its high quality on approximation. Further, we notice that Linformer struggles in this setting: in average its accuracy is worse than Vanilla by 8.22% and Group Attn. by 8.01%. This is because the low-rank projection operation introduces extra model parameters, making Linformer more easily overfit, while overfitting is especially harmful when there are only a few labeled training samples. Triformer and PatchTST, the two timeseries forecasting methods have an accuracy much (34%) lower than Group Attn., for a similar reason to what we have discussed in Sec. 7.2.1. 7.3 Imputation
> In this section, we compare our group attention and the baselines on imputation tasks, a typical data cleaning task in data management. We first show the results on all the 6 datasets in Sec. 7.3.1. We then vary the length of the timeseries on the MGH dataset to show group attention’s scalability on long timeseries in Sec. 7.3.2. 7.3.1 Full-dataset training (Multi-variate imputation)
> Similar to classification tasks, the results of imputation tasks (Table 3) show that Group Attn. consistently outperforms the baselines in training time while achieving comparable/better Mean
> Square Error (MSE). On the large dataset MGH (length = 10,000), TST, Vanilla and PatchTST fail due to out of memory (OOM) errors. Methods using RITA framework (Group Attn., Performer,
> Linformer) all achieve very low MSE and thus are highly accurate. Among them Linformer is the worst. The accuracy of Triformer and PatchTST in general is much lower, because they target forecasting task rather than generating high quality feature embeddings to support various tasks. Here we observe that the longer the timeseries, the larger the speedup is. On the medium sized ECG dataset with a length of 2,000, Group Attn. has a speedup of 5.23/1.65/1.77/5.96/1.43 compared to Vanilla/Performer/Linformer/Triformer/PatchTST. When the length increases to 10,000, the speedup on the MGH dataset increases to 6.59/7.48/54.37 compared to Performer/Linformer/Triformer (Vanilla,TST and PatchTST failed due to out of memory) on imputation task (Table. 3). This is because when the length of the timeseries gets longer, Group Attn. gets more opportunities to find windows with similar properties. Note Triformer is very slow on long series (length = 10,000), because it involves a lot of sequential computation and thus cannot benefit from GPUs. Even on the short WISDM, HHAR, RWHAR, and ET Tdatasets, Group Attn. still consistently outperforms all other methods except PatchTST. This confirms that it fully leverages the similarity among the timeseries windows, while not introducing much overhead. Although PatchTST has comparable speed with Group Attn. on short series, it is much slower on the longer ECG dataset
> (length = 2000) and fails on the very long EEG data (length = 10,000). This is because it concatenates many embeddings to form a very long embedding before making prediction, thus consuming much more GPU memory. This shows PatchTST does not scale to long series. c e s
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
> 21 percentage points because of the expressive power of Transformer. Moreover, the GPU-friendly design of RITA makes it at least 2× faster than GRAIL in training time. 7.5 Ablation Study
> 7.5.1 Adaptive Scheduler
> To evaluate the effectiveness of RITA’s adaptive scheduler (denoted as Dynamic) (Sec. 5), we compare it against (1) baseline Fixed: a fixed group number 𝑁 ; (2) baseline Heuristic: if the validation loss gets lower than ever after the current epoch, we consider that the current 𝑁 is sufficiently large for the current training stage, and set 𝑁 to 𝑁 ∗ 𝐷𝑒𝑐𝑎𝑦_𝑟 𝑎𝑡 𝑒 for the next epoch. RITA: Group Attention is All You Need for Timeseries Analytics 62:21 should decrease gradually. We vary 𝑁 for Fixed, 𝐷𝑒𝑐𝑎𝑦 _𝑟 𝑎𝑡 𝑒 for Heuristic, and the error bound threshold 𝜖 used by RITA.

7.2.2 Pretraining + few label finetune (multi-variate classification)
The results shown in Table 2 get us the following observation:

RITA: 组注意力是时间序列分析的全部所需 62:19
(1) 预训练有效。预训练总是比从头开始使用少量标签进行训练获得更好的准确率。特别是，在WISDM数据上，所有采用RITA架构的方法都至少提高了10%的准确率。考虑到我们没有非常大的无标记预训练集可用，这一表现令人印象深刻。(2) 组注意力相对于TST和TS2VEC的优势。在四个分类数据集中，我们的组注意力平均比TST高出15个百分点，并且比TS2VEC高出6个百分点。(3) 组注意力与其他注意力机制相比的优势。组注意力在4个数据集中的3个上优于Performer和Linformer。与Vanilla相比，在HHAR和ECG数据集上表现更好，而在其他两个数据集上则相当，进一步确认了其近似质量的高质量。此外，我们注意到Linformer在这种设置下存在困难：平均准确率比Vanilla低8.22%，比组注意力低8.01%。这是因为低秩投影操作引入了额外模型参数，使Linformer更容易过拟合，而当仅有少量标记训练样本时，过拟合尤其有害。Triformer和PatchTST这两种时间序列预测方法的准确率明显（34%）低于组注意力，原因与我们在第7.2.1节讨论的原因相似。

7.3 补全
在本节中，我们比较我们的组注意力与其他基线模型在补全任务上的表现，这是数据管理中的典型数据清洗任务。首先展示所有6个数据集（见第7.3.1节）的结果。然后我们在MGH数据集中变化时间序列的长度以显示组注意力在长时序上的可扩展性（见第7.3.2节）。7.3.1 全数据集训练（多变量补全）
与分类任务类似，补全任务（表3）的结果表明，在达到相当或更好的均方误差（MSE）的同时，组注意力在训练时间上始终优于基线模型。在大型数据集MGH（长度=10,000）中，TST、Vanilla和PatchTST因内存溢出错误而失败。采用RITA框架的方法（组注意力、Performer、Linformer）均实现了非常低的MSE，因此具有高度准确性。其中Linformer表现最差。Triformer和PatchTST的整体准确率明显较低，因为它们的目标是预测任务而非生成高质量特征嵌入以支持各种任务。在这里我们观察到时间序列越长，速度提升越大。在长度为2,000的中等规模ECG数据集上，组注意力相比Vanilla/Performer/Linformer/Triformer/PatchTST的速度提升了5.23/1.65/1.77/5.96/1.43倍。当长度增加到10,000时，在补全任务（表3）中，与Performer/Linformer/Triformer相比（Vanilla、TST和PatchTST因内存溢出失败），速度提升达到了6.59/🕸️7.4 与其他非深度学习方法的比较
在本节中，我们对比RITA与非深度学习方法。如图6所示，在所有3个数据集上，由于Transformer的强大表达能力，RITA显著优于GRAIL（当前最先进的非深度学习时间序列表示学习方法）约45、16和21个百分点。此外，RITA的GPU友好设计使其训练速度至少比GRAIL快两倍。

7.5 消融研究
7.5.1 自适应调度器
为了评估RITA自适应调度器（称为Dynamic）的有效性（见第5节），我们将其与以下基线进行比较：(1) 基线Fixed: 固定的组数𝑁；(2) 基线Heuristic: 如果当前epoch后验证损失低于以往最低值，则认为当前𝑁对于当前训练阶段已足够大，并在下一个epoch将𝑁设置为𝑁 ∗ 𝐷𝑒𝑐𝑎𝑦_𝑟 𝑎𝑡 𝑒。RITA：组注意力是时间序列分析的全部所需 62:21 应该逐渐减少。我们变化Fixed中的𝑁，Heuristic中的𝐷𝑒𝑐𝑎𝑦 _𝑟 𝑎𝑡 𝑒以及RITA使用的误差界限阈值𝜖。

> We vary 𝑁 for Fixed, 𝐷𝑒𝑐𝑎𝑦 _𝑟 𝑎𝑡 𝑒 for Heuristic, and the error bound threshold 𝜖 used by RITA. From the results in Table 4 we get the following observations:
> (1) Adaptive Scheduler is better than the baselines. Training with Adaptive Scheduler achieves better or comparable performance compared to the best performing 𝑁 or 𝐷𝑒𝑐𝑎𝑦_𝑟 𝑎𝑡 𝑒 . For 𝐹 𝑖𝑥 𝑒𝑑 , on the MGH dataset, dynamic scheduler always achieves better accuracy and is much faster compared to fixed 𝑁 . On the ECG dataset, although fixed 𝑁 is slightly better than adaptive scheduler in accuracy when setting the 𝑁 as 512, it runs much slower than adaptive scheduler. For
> 𝐻 𝑒𝑢𝑟 𝑖𝑠𝑡 𝑖𝑐 , we have similar observations: on ECG dataset, dynamic scheduler consistently achieves better accuracy than 𝐻 𝑒𝑢𝑟 𝑖𝑠𝑡 𝑖𝑐 . On MGH dataset, dynamic scheduler achieves comparable MSE with less training time. Note that manually finding the best 𝑁 or 𝐷𝑒𝑐𝑎𝑦 _𝑟 𝑎𝑡 𝑒 that balances the accuracy and running time requires careful tuning, while our adaptive scheduler does not need any tuning. (2) Adaptive Scheduler is tuning free. It is robust on both accuracy and running time when 𝜖 varies, while the results of fixed 𝑁 vary significantly when the value of 𝑁 changes. Therefore,
> Adaptive Scheduler frees the users from tuning the 𝜖 threshold, while it is hard to manually find an appropriate 𝑁 or 𝐷𝑒𝑐𝑎𝑦_𝑟 𝑎𝑡 𝑒 for a given dataset. Dataset Task Scheduler Parameter Metric Time
> 1.5 88.34% 292.5
> Dynamic 2 88.48% 236.8
> 3 87.83% 216.8
> 64 87.50% 255.2
> ECG Class. 128 88.96% 297.2
> Fixed 256 88.82% 414.1
> 512 90.03% 662.6
> 1024 88.65% 873.7
> 0.8 85.41% 240.36
> Heuristic
> 0.9 86.28% 253.57
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

RITA：组注意力是时间序列分析的全部所需 62:21 应该逐渐减少。我们变化Fixed中的𝑁，Heuristic中的𝐷𝑒𝑐ａ𝑦 _𝑟 𝑎𝑡 𝑒以及RITA使用的误差界限阈值𝜖。

> Group Attn. Linformer
> Performer
> Triformer
> PatchTST
> TST
> Vanilla
> 0 100 200 300 400 500
> Time Cost / sec
> Fig. 7. Query Execution time for 10,000 10-NN queries. Precision: Vanilla (88.34%), Group Attn.(88.29%),
> Linformer(88.07%), Performer(88.23%/), Triformer(42.45%), PatchTST(80.84%), TST(40.72%). data and finetune each pretrained model with 100 labels per class. The results in Table 5 show that:
> (1) The more pretraining data, the larger the improvement. The accuracy increases with the sizes of the preGtrroauipn Ainttgn. data; The first 20% pretraining data
> (2) Marginal utility diminishing. gives a 10.38% impVraonivlleament in accuracy (72.94% vs 62.56%), while the remaining 80% pretraining data only gives an additional improvement of 2.12% (75.06% vs 72.94%). 0 20 40 60 80 100 120 140 160
> Time Cost / sec
> 7.6 Similarity Search
> We develop a time-series query system to conduct this similarity search experiment. We first use
> RITA to extract feature embeddings from the training set of the ECG dataset and store them in a vector DB. We then use the timeseries in validation set as queries to find their 𝑘 NN from the vector
> DB. Given a query, we use RITA to extract its feature embedding at online query time. In our experiment, we use Postgres [13] as the vector DB, as it features the HNSW index to speed up the high dimensional similarity search. We set the 𝑘 as 10 in 𝑘 NN search and run 10,000 queries. The results, as depicted in Figure 7, show that RITA is faster than all baselines by 60%, indicating that RITA outperforms the baselines on inference time as well. The precision of RITA is on par to that of Vanilla Transformer. Note the precision of Vanillar Transform is considered to be the upper bound of the precision of all Transformer-based methods, because it uses the original expensive attention mechanism without any approximation. RITA outperforms all other baselines in precision, while faster than them. 8 RELATED WORK
> Method TST Vanilla Triformer PatchTST Performer Linformer Group Attn. Time Complexity 𝑂 (𝑛2𝑑 ) 𝑂 (𝑛2𝑑 ) 𝑂 (𝑛𝑑 2 𝑚 ) 𝑂 (𝑛𝑑 2 𝑚 ) 𝑂 (𝑛𝑑 (𝑑 + 𝑃 ) ) 𝑂 (𝑛𝑑 (𝑑 + 𝐿 ) ) 𝑂 (𝑛𝑑 (𝑑 + 𝑁 ) )
> Space Complexity 𝑂 (𝑛2 ) 𝑂 (𝑛2 ) 𝑂 (𝑛𝑑 𝑚 ) 𝑂 (𝑛𝑑 𝑚 ) 𝑂 (𝑛 (𝑑 + 𝑃 ) ) 𝑂 (𝑛 (𝑑 + 𝐿 ) ) 𝑂 (𝑛 (𝑑 + 𝑁 ) )
> Table 6. The time/space complexity of Transformer-based methods. 𝑛: timeseries length; 𝑑 : embedding dimension; 𝑚: number of channels; P,L,N,S,T: method-specific parameters
> 8.1 Timeseries Analytics
> There is a great deal of prior work on timeseries analytics methods. This work can be divided into three categories: (1) non-deep learning methods; (2) CNN/RNN-based deep learning methods; and
> (3) Transformer-based deep learning methods. Traditional Methods. These methods, such as TS-CHIEF [52], HIVE-COTE [38], ROCKET [18] have achieved notable performance on public datasets. Despite that, traditional methods suffer

从表4的结果中得出以下观察：
(1) 自适应调度器优于基线方法。使用自适应调度器进行训练可实现比最佳表现的𝑁或𝐷𝑒𝑐𝑎𝑦_𝑟 𝑎𝑡 𝑒更优或相当的表现。对于Fixed，在MGH数据集上，动态调度器始终取得更好的准确性且速度远快于ervations固定组数。在ECG数据集中提取特征嵌入并存储到向量数据库中后，我们使用验证集中的时间序列作为查询以从该向量数据库中找到其𝑘近邻。给定一个查询，在在线查询时使用RITA提取其特征嵌入。我们的实验中采用Postgres [13] 作为向量数据库，因其具备HNSW索引可加速高维相似性搜索。我们设置𝑘为10并运行10,000次查询。如图7所示的结果表明，RITA比所有基线方法快60%，说明其在推理时间上也优于这些基准模型。RITA的精度与Vanilla Transformer相当。请注意Vanilla Transformer的精度被认为是基于Transformer的方法的上限，因为它使用了原始昂贵注意力机制而无任何近似。RITA在精度方面超越了其他所有基线，并且速度更快。

> RITA: Group Attention is All You Need for Timeseries Analytics 62:23 from one or more issues: they (1) rely on expert knowledge for feature extraction; (2) incur heavy computation cost and are inappropriate for GPU devices; (3) support only uni-variate timeseries;
> (4) perform classification solely. In particular, as the SOTA of timeseries representation learning, GRAIL [47] extracts landmarks from data and computes the representations with the combination of the landmarks. However,
> GRAIL only supports uni-variate timeseries. Our experiments (Sec. 7.4) show that RITA outperforms
> GRAIL in both effectiveness and efficiency on uni-variate timeseries. CNN/RNN-based Deep Learning Methods. CNN-based methods, such as InceptionTime [25] and Resnet [23], are good at classification tasks, but can not handle generative tasks such as forecasting because of the inductive bias of convolution networks. TS2VEC [68] is the SOTA non-Transformer representation learning method which uses CNN architecture. As confirmed in experiments, RITA consistently outperform it. RNN-based methods, such as Brit [8] and deepAR [51], support classification, regression and generation. However, the recurrent structure brings a lot of problems: (1) limiting the model’s ability in capturing long-range correlation; (2) notoriously difficult to train [48] because of gradient vanishing and exploding problem. As a result, such methods can hardly scale to very long timeseries. Transformer-based Deep Learning Methods. Given that Transformer is the best choice for backbone in almost all sequence modeling tasks, some effort has been made to apply Transformer to timeseries analytics. In timeseries forecasting, LogTrans [35] introduced a log sparsity assumption to attention computation. Informer [71] pushes LogTrans a step further and scales forecasting to multi-variate timeseries. Autoformer [65] performs forecasting by decomposing timeseries into the trend part and the seasonal part. FEDformer [72] proposed a Frequency Enhanced Attention with Fourier
> Transform. Pyraformer [40] and Triformer [12] used hierarchical attention structures. PatchTST [46] introduced a patching pattern in attention. In our experiments, among this big family, we choose
> Triformer and PatchTST as our baselines, because they experimentally outperform the others and are considered as SOTA in this field. Because these methods are tailored for timeseries forecasting, the feature embeddings produced by their specialized designs may have adverse effects on other timeseries analytical tasks.

8 相关工作
方法 TST Vanilla Triformer PatchTST Performer Linformer Group Attn. 时间复杂度 𝑂 (𝑛²𝑑 ) 𝑂 (𝑛²𝑑 ) 𝑂 (𝑛𝑑 2 𝑚 ) 𝑂 ( nad 2 m ) 𝑂 (nad(d + P )) 𝑂 (n d (d + L )) 𝑂 (n d (d + N ))
空间复杂度 𝑂 (n²) 𝑂 (n²) 𝑂 (ndm) 𝑂 (ndm) 𝑂 (n(d+P)) 𝑂 (n(d+L)) 𝑂 (n(d+N))
表6. 基于Transformer的方法的时间/空间复杂度。𝑛: 时间序列长度；𝑑 : 嵌入维度；𝑚: 通道数；P,L,N,S,T: 方法特定参数

8.1 时间序列分析
在时间序列分析方法上已有大量先前工作。这项工作可分为三类：(1) 非深度学习方法； (2) CNN/RNN基的深度学习方法； 和 (3) 基于Transformer的深度学习方法。传统方法。这些方法，如TS-CHIEF [52]、HIVE-COTE [38]、ROCKET [18] 在公共数据集上取得了显著表现。尽管如此，传统方法仍面临一个或多个问题：它们 (1) 依赖专家知识进行特征提取；(2) 计算成本高昂且不适合GPU设备；(3) 仅支持单变量时间序列； (4) 仅执行分类任务。特别是作为时间序列表示学习的SOTA（最先进），GRAIL [47] 从数据中提取地标并结合这些地标计算表示。然而， GRAIL 只能处理单变量时间序列。我们的实验(第7.4节)表明，在单变量时间序列上RITA在效果和效率方面均优于GRAIL。

CNN/RNN基的深度学习方法。基于CNN的方法如InceptionTime [25] 和Resnet [23] 在分类任务中表现良好，但由于卷积网络的归纳偏差无法处理生成性任务（如预测）。TS2VEC [68] 是SOTA非Transformer表示学习方法，采用CNN架构。实验确认了RITA始终优于它。基于RNN的方法如Brit [8] 和deepAR [51] 支持分类、回归和生成。然而，循环结构带来许多问题： (1) 限制模型捕捉长程相关的能力；(2) 因梯度消失/爆炸问题而训练困难[48]。因此，这些方法难以扩展到非常长的时间序列。

基于Transformer的深度学习方法。鉴于Transformer在几乎所有序列建模任务中都是最佳选择，一些努力已用于将Transformer应用于时间序列分析。在时间序列预测领域，LogTrans [35] 引入了对注意力计算的日志稀疏性假设。Informer [71] 进一步推动LogTrans，并扩展预测到多变量时间序列。Autoformer [65] 通过分解时间序列为趋势部分和季节部分进行预测。FEDformer [72] 提出了一种基于傅里叶变换的频率增强注意力机制。Pyraformer [40] 和Triformer [12] 使用了层次化注意力结构。PatchTST [46] 在注意力中引入了分块模式。在我们的实验中，从这一大家族中我们选择Triformer和PatchTST作为基线模型，因为它们实验证明优于其他方法，并被认为是该领域的SOTA（最先进）。由于这些方法专门针对时间序列预测设计，其专有设计方案生成的特征嵌入可能对其他时间序列分析任务产生负面影响。

> designs may have adverse effects on other timeseries analytical tasks. For instance, Triformer incorporates sequence compression operations, which can be detrimental for imputation due to the potential loss of vital information on the entire timeseries. Moreover,
> Triformer employs variable-specific modeling, computing embeddings for each input channel separately. While this approach may be beneficial for forecasting tasks, it may not be suitable for classification, as the latter necessitates the consideration of information from all channels simultaneously. For imputation tasks, CDSA [43] outperforms statistical methods and the SOTA RNN-based method Brit [8]. For timeseries classification, AutoTransformer [50] performs architecture search to adapt to tasks in different domains. For timeseries anomaly detection, Anomaly Transformer [66] outperforms many widely used methods such as OmniAnomaly [54], assuming the attention score maps show Gaussian distribution. All of these works are designed for specific tasks, rather than a representation learning framework to serve different downstream tasks. To fill this gap, some researchers proposed a
> Transformer-based architecture, called TST [70]. Like RITA, TST supports regression, classification, and unsupervised learning through the “cloze test” pretraining task on timeseries. However, TST directly uses the classical Vanilla self-attention, thus not scalable to long timeseries as shown in our experiments (Sec. 7). 8.2 Efficient Transformers
> The need to improve the scalability of Transformers has led to more efficient variations, especially for accommodating long text data in NLP [56]. A first step was to introduce fixed/random patterns to the self-attention mechanism. Sparse Transformer [10] and Longformer [4] only compute attention at fixed intervals. ETC [2] and BigBird [69] use global-local attention: the computation is limited within a fixed radius, while some auxiliary tokens are added to attend/get attended globally. However, fixed attention patterns heavily depends on users to give an optimal setting. Reformer [31] proposed only computing the dominant attention terms based on their observation of sparsity in attention matrix from language/image data. Such sparsity is intuitive in language data, in which a word’s attention mainly focuses on the nearby sentences. However, attention in timeseries data shows strong seasonal patterns rather than sparse patterns, mainly as result of the periodicity of timeseries data. Therefore, such works do not work well for timeseries. Apart from introducing attention patterns, some works seek to solve this problem with applied mathematics techniques. Linformer [62] performs a projection to decrease the size of query, key and value matrices before attention computation, because the attention matrix tends to be low-ranked. Performer [11] uses linear functions to approximate the kernel function softmax, making attention computation commutative. Linformer and Performer do not depend on the unique properties of language data, thus potentially fitting timeseries better than other techniques, which is why we compared against them in our experiments. However as shown in Sec. 7, our group attention significantly outperforms them in both accuracy and efficiency (training time), because group attention fully leverages the periodicity of timeseries. In Table 6, we summarize the time/space complexity of the works that target scale Transformers to long sequence. Note although several methods claim linear time/space complexity, their complexities all involve a method-specific constant, similar to the number of groups 𝑁 in our group attention. In the long time series scenarios, when 𝑑 ∈ [64, 128, 256] and 𝑛 ≫ 𝑑 ≈ (common settings) where 𝑑 denotes the dimension of feature embeddings and 𝑛 represents the length of the timeseries, the theoretical complexities of PatchTST, Triformer, Linformer, and Performer are at the same magnitude to group attention. However, our empirical experiments show that Group Attention consistently and significantly outperforms these methods in terms of efficiency, as shown in Fig. 4, Fig. 5, Table 3. This is because our group attention is well-suited to long time series. The longer the timeseries is, the more opportunity group attention has to find the similar segments and group them together. This leads to a slower growth rate in the number of groups ‘N’ – the constant in the time/space complexities of group attention. 9 CONCLUSION
> In this work, we presented RITA, an automatic, self-supervised, and scalable timeseries embedding tool. RITA effectively adapts Transformer, popular in NLP, to embed timeseries segments into feature vectors. As the key component of RITA, group attention eliminates the performance bottleneck of the classical self-attention mechanisms, thus successfully scaling RITA to highly complex, long timeseries data. Our experiments confirm that RITA significantly speeds up existing attention mechanisms by 63X with a better accuracy.

由于这些方法专门针对时间序列预测设计，其专有设计方案生成的特征嵌入可能对其他时间序列分析任务产生负面影响。例如，Triformer引入了序列压缩操作，这可能会因整个时间序列关键信息潜在丢失而对缺失值填补造成不利影响。此外，Triformer采用了变量特定建模方式，在计算每个输入通道的嵌入时分别进行处理。虽然这种方法可能有利于预测任务，但未必适合分类任务，因为后者需要同时考虑所有通道的信息。对于缺失值填补任务，CDSA [43] 优于统计方法和最先进（SOTA）的RNN基方法Brit [8]。对于时间序列分类，AutoTransformer [50] 进行了架构搜索以适应不同领域的任务。对于时间序列异常检测，Anomaly Transformer [66] 在许多广泛应用的方法如OmniAnomaly [54] 上表现更优，假设注意力得分图显示高斯分布。所有这些工作都是针对特定任务设计的，而非用于服务不同下游任务表示学习框架。为填补这一空白，一些研究者提出了一种基于Transformer架构称为TST [70] 的方法。与RITA类似，TST通过在时间序列上进行"填空测试"预训练任务支持回归、分类和无监督学习。然而，TST直接使用经典的Vanilla自注意力机制，在我们的实验（第7节）中显示无法扩展到长时序数据。

8.2 高效Transformer
提升Transformer可扩展性的需求促使了更多高效变体的出现，特别是为了适应NLP中的长文本数据[56]。第一步是向自注意力机制引入固定/随机模式。Sparse Transformer [10] 和Longformer [4] 仅在固定间隔内计算注意力。ETC [2] 和BigBird [69] 使用全局-局部注意力：计算限制在固定半径范围内，同时添加一些辅助标记以实现全局关注和被关注。然而，固定的注意力模式严重依赖用户给出最优设置。Reformer [31] 基于对语言/图像数据中注意力矩阵稀疏性的观察，仅计算主导的注意力项。这种稀疏性在语言数据中是直观的，在其中单词的关注主要集中在附近句子上。但时间序列数据中的注意力表现出强烈的季节模式而非稀疏模式，这主要是由于时间序列数据的周期性所致。因此，这些方法对于时序数据效果不佳。除了引入注意力模式外，一些工作尝试通过应用数学技术解决此问题。Linformer [62] 在计算注意力前对查询、键和值矩阵进行投影以降低其规模，因为注意力矩阵往往具有低秩特性。Performer [11] 使用线性函数近似softmax核函数，使注意力计算可交换化。Linformer和Performer不依赖语言数据的独特属性，因此可能比其他技术更适合时间序列，这也是我们在实验中与它们进行比较的原因。然而如第7节所示，在准确性和效率（训练时间）方面我们的组注意力显著优于这些方法，因为组注意力充分利用了时序的周期性特性。表6总结了针对扩展Transformer到长序列的工作的时间/空间复杂度。注意尽管几种方法声称具有线性时间/空间复杂度，但它们的所有复杂度都包含特定方法常数项，类似于我们组注意力中的分组数量𝑁。在长时序场景中，当𝑑 ∈ [64, 128, 256]且𝑛 ≫ 𝑑 ≈（常见设置）其中𝑑表示特征嵌入的维度而𝑛代表时间序列长度时，PatchTST、Triformer、Linformer和Performer的理论复杂度与组注意力处于相同量级。然而我们的实验证明，在效率方面组注意力始终显著优于这些方法，如图4、图5和表3所示。这是因为我们的组注意力特别适合长时序数据。时间序列越长，组注意力就越有机会找到相似片段并将其分组在一起。这导致了分组数量'𝑁'的更慢增长速率——即组注意力的时间/空间复杂度中的常数项。

9 结论
在本工作中，我们提出了RITA，一种自动、自监督且可扩展的时间序列嵌入工具。RITA有效将NLP中流行的Transformer应用于时间序列片段到特征向量的映射。作为RITA的核心组件，组注意力消除了经典自注意力机制的表现瓶颈，从而成功地将RITA扩展至高度复杂和长时序数据。我们的实验确认了RITA通过63倍的速度提升显著优于现有注意力机制，在准确率方面也表现更优。
