"""[BERT](https://arxiv.org/abs/1810.04805)

BERT(Bidirectional Encoder Representations from Transformers) has the following components:

1. Embedding layers
2. Attention Mask
3. Encoder layer
   1. Multi-head attention
      1. Scaled dot product attention
      2. Position-wise feed-forward network
4. BERT (assembling all the components
"""

import math
import re
from random import *
import numpy as np

import torch
import torch.nn as nn
import torch.optim as optim

print("MODULES LOADED")

"""Embedding Layer

The embedding is the first layer in BERT that takes the input and creates a lookup table. The parameters of the embedding layers are learnable, which means when the learning process is over the embeddings will cluster similar words together. 

The embedding layer also preserves different relationships between words such as: semantic, syntactic, linear, and since BERT is bidirectional it will also preserve contextual relationships as well. 

In the case of BERT, it creates three embeddings for 

Token,Position and Segments.

If you recall we haven’t created a function that takes the input and formats it for position embedding but the formatting for token and segments are completed. So we will take the input and create a position for each word in the sequence
"""

class EmbeddingLayer(nn.Module):
   def __init__(self):
      super(EmbeddingLayer,self).__init__()
      self.token_embedding = nn.Embedding(vocab_size,d_model)
      self.position_embedding = nn.Embedding(maxlen,d_model)
      self.segment_embedding = nn.Embedding(n_segments,d_model)
      self.norm = nn.LayerNorm(d_model)

   def forward(self,x,seg):
      seq_len = x.size(1)
      pos = torch.arange(seq_len,dtype=torch.long)  
      #(seq_len,) --> (batch_size,seq_len)
      pos = pos.unsqueeze(0).expand_as(x)
      embedding = self.token_embedding(x) + self.position_embedding(pos) + self.segment_embedding(seg)
      return self.norm(embedding)

"""Attention Mask
Attention masks allow us to send a batch into the transformer even when the examples in the batch have varying lengths.

eg:
[CLS] The cat is walking [PAD] [PAD] [PAD]. [CLS] The dog is barking at the tree.

The length of the first sentence is equal to the length of the second sentence.
"""

def get_attention_pad_mask(seq_q,seq_k):
    batch_size,len_q = seq_q.size()
    batch_size,len_k = seq_k.size()
    pad_attn_mask = seq_k.data.eq(0).unsqueeze(1)  # batch_size x 1 x len_k(=len_q), one is masking
    return pad_attn_mask.expand(batch_size, len_q, len_k)  # batch_size x len_q x len_k

"""Encoder Layer
The encoder has two main components: 

1. Multi-head Attention
2. Position-wise feed-forward network.
 
The work of the encoder is to find representations and patterns from the input and attention mask.
"""

class EncoderLayer(nn.Module):
   def __init__(self):
      super(EncoderLayer,self).__init__()
      self.enc_self_attn = MultiHeadAttention()
      self.pos_ffn = PositionWiseFeedForward()

   def forward(enc_inputs,enc_self_attn_mask):
      enc_outputs, attn = self.enc_self_attn(enc_inputs, enc_inputs, enc_inputs, enc_self_attn_mask) # enc_inputs to same Q,K,V
      enc_outputs = self.pos_ffn(enc_outputs) # enc_outputs: [batch_size x len_q x d_model]
      return enc_outputs, attn

"""Multi Head Attention

This is the first of the main components of the encoder. 

The attention model takes three inputs: Query, Key, and Value.  

Multihead attention takes four inputs: Query, Key, Value, and Attention mask. The embeddings are fed as input to the Query, Key, and Value argument, and the attention mask is fed as input to the attention mask argument. 
These three inputs and the attention mask are operated with a dot product operation that yields two outputs: context vectors and attention. The context vector is then passed through a linear layer and finally that yields the output.
"""

class MultiHeadAttention(nn.Module):
   def __init__(self):
      super(MultiHeadAttention,self).__init__()
      self.WQ = nn.Linear(d_model,d_k * n_heads)
      self.WK = nn.Linear(d_model,d_k * n_heads)
      self.WV = nn.Linear(d_model,d_v * n_heads)

   def forward(self,Q,K,V,attn_mask):
      # q: [batch_size x len_q x d_model], k: [batch_size x len_k x d_model], v: [batch_size x len_k x d_model]
      residual,batch_size = Q,Q.size(0)
      # (B, S, D) -proj-> (B, S, D) -split-> (B, S, H, W) -trans-> (B, H, S, W)
      q_s = self.WQ(Q).view(batch_size, -1, n_heads, d_k).transpose(1,2)  # q_s: [batch_size x n_heads x len_q x d_k]
      k_s = self.WK(K).view(batch_size, -1, n_heads, d_k).transpose(1,2)  # k_s: [batch_size x n_heads x len_k x d_k]
      v_s = self.WV(V).view(batch_size, -1, n_heads, d_v).transpose(1,2)  # v_s: [batch_size x n_heads x len_k x d_v]
      
      # attn_mask : [batch_size x n_heads x len_q x len_k]
      attn_mask = attn_mask.unsqueeze(1).repeat(1,n_heads,1,1)

      # context: [batch_size x n_heads x len_q x d_v], attn: [batch_size x n_heads x len_q(=len_k) x len_k(=len_q)]
      context, attn = ScaledDotProductAttention()(q_s, k_s, v_s, attn_mask)
      context = context.transpose(1, 2).contiguous().view(batch_size, -1, n_heads * d_v) # context: [batch_size x len_q x n_heads * d_v]
      output = nn.Linear(n_heads * d_v, d_model)(context)

      return nn.LayerNorm(d_model)(output + residual), attn # output: [batch_size x len_q x d_model]

"""Scaled Dot Product Attention
The scaled dot product attention class takes four arguments: Query, Key, Value, and Attention mask. Essentially, the first three arguments are fed with the word embeddings and the attention mask argument is fed with attention mask embeddings.
Then it does a matrix multiplication between query and key to get scores. 
Following that we use scores.masked_fill_(attn_mask, -1e9) . This attribute fills the element of scores with -1e9 where the attention masks are True while the rest of the elements get an attention score which is then passed through a softmax function that gives a score between 0 and 1. Finally, we perform a matrix multiplication between attention and values which gives us the context vectors.
"""

class ScaledDotProductAttention(nn.Module):
   def __init__(self):
       super(ScaledDotProductAttention, self).__init__()

   def forward(self, Q, K, V, attn_mask):
       scores = torch.matmul(Q, K.transpose(-1, -2)) / np.sqrt(d_k) # scores : [batch_size x n_heads x len_q(=len_k) x len_k(=len_q)]
       scores.masked_fill_(attn_mask, -1e9) # Fills elements of self tensor with value where mask is one.
       attn = nn.Softmax(dim=-1)(scores)
       context = torch.matmul(attn, V)
       return score, context, attn

"""Position Wise Feed-Forward Layer"""

class PositionWiseFeedForward(nn.Module):
    def __init__(self):
        super(PositionWiseFeedForward, self).__init__()
        self.fc1 = nn.Linear(d_model, d_ff)
        self.fc2 = nn.Linear(d_ff, d_model)

    def forward(self, x):
        # (batch_size, len_seq, d_model) -> (batch_size, len_seq, d_ff) -> (batch_size, len_seq, d_model)
        return self.fc2(gelu(self.fc1(x)))

"""GeLU Activation"""

def gelu(x):
    "Implementation of the GeLU activation function"
    return x * 0.5 * (1.0 + torch.erf(x / math.sqrt(2.0)))

"""Making Batches"""

def make_batch():
    batch = []
    positive = negative = 0
    while positive != batch_size/2 or negative != batch_size/2:
        tokens_a_index, tokens_b_index= randrange(len(sentences)), randrange(len(sentences)) # sample random index in sentences
        tokens_a, tokens_b= token_list[tokens_a_index], token_list[tokens_b_index]
        input_ids = [word_dict['[CLS]']] + tokens_a + [word_dict['[SEP]']] + tokens_b + [word_dict['[SEP]']]
        segment_ids = [0] * (1 + len(tokens_a) + 1) + [1] * (len(tokens_b) + 1)

        # MASK LM
        n_pred =  min(max_pred, max(1, int(round(len(input_ids) * 0.15)))) # 15 % of tokens in one sentence
        cand_maked_pos = [i for i, token in enumerate(input_ids)
                          if token != word_dict['[CLS]'] and token != word_dict['[SEP]']]
        shuffle(cand_maked_pos)
        masked_tokens, masked_pos = [], []
        for pos in cand_maked_pos[:n_pred]:
            masked_pos.append(pos)
            masked_tokens.append(input_ids[pos])
            if random() < 0.8:  # 80%
                input_ids[pos] = word_dict['[MASK]'] # make mask
            elif random() < 0.5:  # 10%
                index = randint(0, vocab_size - 1) # random index in vocabulary
                input_ids[pos] = word_dict[number_dict[index]] # replace

        # Zero Paddings
        n_pad = maxlen - len(input_ids)
        input_ids.extend([0] * n_pad)
        segment_ids.extend([0] * n_pad)

        # Zero Padding (100% - 15%) tokens
        if max_pred > n_pred:
            n_pad = max_pred - n_pred
            masked_tokens.extend([0] * n_pad)
            masked_pos.extend([0] * n_pad)

        if tokens_a_index + 1 == tokens_b_index and positive < batch_size/2:
            batch.append([input_ids, segment_ids, masked_tokens, masked_pos, True]) # IsNext
            positive += 1
        elif tokens_a_index + 1 != tokens_b_index and negative < batch_size/2:
            batch.append([input_ids, segment_ids, masked_tokens, masked_pos, False]) # NotNext
            negative += 1
    return batch

"""Model Class"""

class BERT(nn.Module):
   def __init__(self):
      super(BERT,self).__init__()
      self.embedding = EmbeddingLayer()
      self.layers = nn.ModuleList([EncoderLayer() for _ in range(n_layers)])
      self.fc = nn.Linear(d_model, d_model)
      self.activ1 = nn.Tanh()
      self.linear = nn.Linear(d_model, d_model)
      self.activ2 = gelu
      self.norm = nn.LayerNorm(d_model)
      self.classifier = nn.Linear(d_model, 2)
      # decoder is shared with embedding layer
      embed_weight = self.embedding.token_embedding.weight
      n_vocab, n_dim = embed_weight.size()
      self.decoder = nn.Linear(n_dim, n_vocab, bias=False)
      self.decoder.weight = embed_weight
      self.decoder_bias = nn.Parameter(torch.zeros(n_vocab))

   def forward(self, input_ids, segment_ids, masked_pos):
        output = self.embedding(input_ids, segment_ids)
        enc_self_attn_mask = get_attn_pad_mask(input_ids, input_ids)
        for layer in self.layers:
            output, enc_self_attn = layer(output, enc_self_attn_mask)
        # output : [batch_size, len, d_model], attn : [batch_size, n_heads, d_mode, d_model]
        # it will be decided by first token(CLS)
        h_pooled = self.activ1(self.fc(output[:, 0])) # [batch_size, d_model]
        logits_clsf = self.classifier(h_pooled) # [batch_size, 2]

        masked_pos = masked_pos[:, :, None].expand(-1, -1, output.size(-1)) # [batch_size, max_pred, d_model]
        # get masked position from final output of transformer.
        h_masked = torch.gather(output, 1, masked_pos) # masking position [batch_size, max_pred, d_model]
        h_masked = self.norm(self.activ2(self.linear(h_masked)))
        logits_lm = self.decoder(h_masked) + self.decoder_bias # [batch_size, max_pred, n_vocab]

        return logits_lm, logits_clsf

if __name__ == '__main__':
    # BERT Parameters
    maxlen = 30 # maximum length
    batch_size = 6
    max_pred = 5  # max tokens of prediction
    n_layers = 12 # number of Encoder Layer
    n_heads = 12 # number of heads in Multi-Head Attention
    d_model = 768 # Embedding Size
    d_ff = 768 * 4  # 4*d_model, FeedForward dimension
    d_k = d_v = 64  # dimension of K(=Q), V
    n_segments = 2

    text = (
        'Hello, how are you? I am Romeo.\n'
        'Hello, Romeo My name is Juliet. Nice to meet you.\n'
        'Nice meet you too. How are you today?\n'
        'Great. My baseball team won the competition.\n'
        'Oh Congratulations, Juliet\n'
        'Thanks you Romeo'
    )
    sentences = re.sub("[.,!?\\-]", '', text.lower()).split('\n')  # filter '.', ',', '?', '!'
    word_list = list(set(" ".join(sentences).split()))
    word_dict = {'[PAD]': 0, '[CLS]': 1, '[SEP]': 2, '[MASK]': 3}
    for i, w in enumerate(word_list):
        word_dict[w] = i + 4
    number_dict = {i: w for i, w in enumerate(word_dict)}
    vocab_size = len(word_dict)

    token_list = list()
    for sentence in sentences:
        arr = [word_dict[s] for s in sentence.split()]
        token_list.append(arr)

    model = BERT()

"""Training"""

criterion = nn.CrossEntropyLoss()
optimizer = optim.Adam(model.parameters(), lr=0.001)

batch = make_batch()
input_ids, segment_ids, masked_tokens, masked_pos, isNext = map(torch.LongTensor, zip(*batch))

for epoch in range(100):
    optimizer.zero_grad()
    logits_lm, logits_clsf = model(input_ids, segment_ids, masked_pos)
    loss_lm = criterion(logits_lm.transpose(1, 2), masked_tokens) # for masked LM
    loss_lm = (loss_lm.float()).mean()
    loss_clsf = criterion(logits_clsf, isNext) # for sentence classification
    loss = loss_lm + loss_clsf
    if (epoch + 1) % 10 == 0:
         print('Epoch:', '%04d' % (epoch + 1), 'cost =', '{:.6f}'.format(loss))
    loss.backward()
    optimizer.step()

# Predict mask tokens ans isNext
input_ids, segment_ids, masked_tokens, masked_pos, isNext = map(torch.LongTensor, zip(batch[0]))
print(text)
print([number_dict[w.item()] for w in input_ids[0] if number_dict[w.item()] != '[PAD]'])

logits_lm, logits_clsf = model(input_ids, segment_ids, masked_pos)
logits_lm = logits_lm.data.max(2)[1][0].data.numpy()
print('masked tokens list : ',[pos.item() for pos in masked_tokens[0] if pos.item() != 0])
print('predict masked tokens list : ',[pos for pos in logits_lm if pos != 0])

logits_clsf = logits_clsf.data.max(1)[1].data.numpy()[0]
print('isNext : ', True if isNext else False)

print('isNext : ', True if isNext else False)
print('predict isNext : ',True if logits_clsf else False)
