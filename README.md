# GoodWiki Dataset

GoodWiki is a 179 million token dataset of English Wikipedia articles collected on **September 4, 2023**, that have been marked as [Good](https://en.wikipedia.org/wiki/Wikipedia:Good_articles) or [Featured](https://en.wikipedia.org/wiki/Wikipedia:Featured_articles) by Wikipedia editors. The dataset provides these articles in [GitHub-flavored Markdown](https://github.github.com/gfm/) format, preserving layout features like lists, code blocks, math, and block quotes, unlike many other public Wikipedia datasets. Articles are accompanied by a short description of the page as well as any associated categories.

Thanks to a careful conversion process from wikicode, the markup language used by Wikipedia, articles in GoodWiki are generally faithful reproductions of the corresponding original Wikipedia pages, minus references, files, infoboxes, and tables. Curated template transclusion and HTML tag handling have minimized instances where entire words and phrases are missing mid-sentence like in other public Wikipedia datasets.

The hope is that this more comprehensive data will play a small role in improving open-source NLP efforts in language modeling, summarization, and instruction tuning.

GoodWiki is more than 1.5 times larger (when compared using the same tokenizer) than the widely used [WikiText-103](https://huggingface.co/datasets/wikitext) dataset by Merity et al., even after excluding article descriptions. Also limited to articles marked as Good or Featured, WikiText inspired GoodWiki.

## Table of Contents

* [Composition](#composition)
	* [Languages](#languages)
	* [Markdown Details](#markdown-details)
* [Methodology](#methodology)
	* [Alternatives Considered](#alternatives-considered)
* [Limitations](#limitations)
* [Future Work](#future-work)
* [License](#license)
* [Citation](#citation)
* [Feedback and Contributions](#feedback-and-contributions)

## Composition

The dataset consists of **44,754 rows** in a **482.7 MB** snappy-compressed Parquet file. Each row consists of the following fields:

* `pageid` (`int64`): The Wikipedia id of the article.
* `title` (`string`): The title of the article.
* `revid` (`int64`): The Wikipedia id of the revision used.
* `description` (`string | null`): Plaintext short description/summary of the article written by Wikipedia contributors.
* `categories` (`list[string]`): The article's Wikipedia categories.
* `markdown` (`string`): The content of the article in GitHub-flavored Markdown format.

Here's an example row in JSON format:

```json
{
	"pageid": 40961074,
	"title": "Attarsiya",
	"revid": 1164804042,
	"description": "Military leader of Ahhiya",
	"categories": [
		"Ancient Anatolia",
		"Greek military leaders",
		"Mycenaean Greeks"
	],
	"markdown": "Attarsiya was a 15th–14th century BCE military leader of Ahhiya. In the Hittite archives of circa 1400 BCE, he is described as a \"man of Ahhiya\", a country identified with the Achaeans and Mycenaean Greece. The campaigns of Attarsiya, as well as his conflict with the Hittite vassal, Madduwatta, represent the first recorded Mycenaean Greek military activity on the Anatolian mainland, as well as the first conflict between Achaeans and Hittites...",
}
```

The markdown field contains a total of **179,198,101 tokens** tokenized using HuggingFace's pretrained `facebook/opt-350m` tokenizer. It also contains **811,791,686 characters** and **132,691,055 words**.

Even with the markdown formatting, GoodWiki can also be used as a plaintext dataset as markdown formatting syntax is fairly minimal.

### Languages

While articles are taken exclusively from English Wikipedia, they sometimes contain small snippets from other languages as well as recurring use of the [International Phonetic Alphabet](https://en.wikipedia.org/wiki/International_Phonetic_Alphabet) in article ledes. Some articles include code blocks in pseudocode as well as in popular programming languages.

### Markdown Details

GoodWiki articles follow the GitHub-flavored Markdown spec, including for blockquotes, code blocks, and lists. Bolding, italicizing, underlining, and strikethroughs have been removed as they introduce a lot of noise especially in math/computing articles.

Some markdown details are worth highlighting:

#### Math

Content in math templates and XML tags are enclosed in markdown with `$` delimiters. For example,

```xml
<math>O(n^2)</math>
```

becomes: `$O(n^2)$`.

#### Super/Subscript

Superscripts and subscripts are denoted using `<sup></sup>` and `<sub></sub>` tags respectively.

#### \$ and \#

Dollar signs and hashes are escaped with `\` to avoid interfering with math and heading syntax.

## Methodology

On the evening of September 4, 2023 PT, we downloaded the wikicode of articles associated with the [Good](https://en.wikipedia.org/wiki/Category:Good_articles) and [Featured](https://en.wikipedia.org/wiki/Category:Featured_articles) categories in the main namespace (`ns=0`) on Wikipedia via the [Query API](https://www.mediawiki.org/wiki/API:Query).

After some preprocessing including removing comments, applying magic code, and removing unrecognized or unnecessary template tags, we sent the resulting code to Wikipedia's [Expandtemplates API](https://www.mediawiki.org/wiki/API:Expandtemplates). This endpoint [transcludes](https://en.wikipedia.org/wiki/Help:Transclusion) template tags, turning them into HTML and plaintext. We chose the templates to transclude by counting all the templates used across the dataset and selecting the ones that are not rare, not used for citations, and not used for asides like infoboxes and tables.

The Expandtemplates output is then postprocessed. During this phase, we remove sections associated with references (e.g. `Sources Cited`), extract text from wikilinks and external links, delete media links, and handle [HTML tags](https://en.wikipedia.org/wiki/Help:HTML_in_wikitext). The postprocessed output is then converted to GitHub-flavored Markdown using [Pandoc](https://pandoc.org/). We also discarded articles detected by Pandoc to have corrupt wikicode (`n=125`).

The markdown output is then cleaned using regular expressions to remove excessive spacing, empty list items, unnecessary escaping, and resolve other problems with Pandoc's conversion. We normalized the markdown output unicode to a composed form (NFKC).

### Alternatives Considered

#### Converting End-To-End Using Pandoc

While Pandoc can in theory convert raw wikicode to markdown, it is **not** a complete wikicode parser and therefore often produces errant output without preprocessing. Furthermore, direct conversion of raw wikicode would lose a lot of the content attached to wikicode templates as Pandoc cannot perform transclusion.

#### Using TextExtracts API

Wikipedia has a [TextExtracts](https://www.mediawiki.org/wiki/Extension:TextExtracts#API) API that directly outputs a limited HTML or plaintext output of a page given that page's title. In practice, I've found the HTML output generated by this endpoint to often contain malformed or incomplete HTML with injected references that are difficult to parse. The plaintext output was also often poor, including reference artifacts and missing content.

Other caveats are listed [here](https://www.mediawiki.org/wiki/Extension:TextExtracts#API) and were the reasons why this approach was discarded.

#### Transcluding All Templates

During the preprocessing process, we eliminate templates outside of a given subset. We did this because we found that transcluding all templates injected a lot of noise in the output, including janky HTML, styles, references, and unnecessary content. This noise made parsing difficult and error-prone, resulting in poor quality markdown littered with artifacts similar to those visible in the TextExtracts output.

Transcluding a subset largely solved these issues while still preserving as much content as possible.

## Limitations

* Chemical equations sometimes include formatting issues like unnecessary line-breaks. These equations, however, are rare.
* In articles about ancient civilizations and languages, rare Unicode characters are occasionally included in the markdown. It might be worth removing these characters during the tokenization process.
* In rare cases, book/article names may be missing from the markdown as they are considered citations in the wikicode.
* Inflation data is missing from some articles. These articles use the `Inflation` template tag to include this information, which works poorly with the Extracttemplates API.
* Articles may feature empty sections due to table/box removal.
* Some code blocks are denoted using indents instead of formal code blocks. This is due to the original wikicode not denoting them as such.
* Template subset allowing transclusion will probably need to be updated for use in future data dumps. The list of templates used on Wikipedia is constantly evolving.

## Future Work

Time permitting, we hope to apply this careful conversion/generation process on all of English Wikipedia which will require our conversion script to be much faster and better parallelized. We also hope to extract other information from pages like entries in infoboxes that could be useful for question answering and instruction tuning applications.

If you're interested in helping out, please reach out!

## License

The dataset and accompanying code are licensed under an **MIT license**. Pandoc, which must be downloaded separately, is GPL-licensed.

While this project is permissively licensed, we hope that you contribute any improvements you make to this dataset to this repo.

## Citation

If you use the GoodWiki Dataset in your research or projects, please cite it using the following citation:

```tex
@misc{GoodWiki,
  title = {GoodWiki Dataset},
	author = {Choi, Euirim},
  howpublished = {\url{https://www.github.com/euirim/goodwiki}},
	month = {September},
	year = {2023}
}
```

## Feedback and Contributions

Contributions via pull requests are welcome. Please submit bugs and feature requests via GitHub's issue tracker. If you don't know how you could help improve this project, please look at the [Future Work](#future-work) section.

Was this dataset useful for your work? Please let us know. We'd love to feature your project :)
