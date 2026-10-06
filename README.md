[image-post-embed]: https://raw.githubusercontent.com/MinnDevelopment/fxreddit/master/assets/image-post-embed.png
[gallery-post-embed]: https://raw.githubusercontent.com/MinnDevelopment/fxreddit/master/assets/gallery-post-embed.png
[video-post-embed]: https://raw.githubusercontent.com/MinnDevelopment/fxreddit/master/assets/video-post-embed.gif
[youtube-post-embed]: https://raw.githubusercontent.com/MinnDevelopment/fxreddit/master/assets/youtube-post-embed.gif
[article-post-embed]: https://raw.githubusercontent.com/MinnDevelopment/fxreddit/master/assets/article-post-embed.png
[tweet-post-embed]: https://raw.githubusercontent.com/MinnDevelopment/fxreddit/master/assets/tweet-post-embed.png
[twitch-post-embed]: https://raw.githubusercontent.com/MinnDevelopment/fxreddit/master/assets/twitch-post-embed.gif
[poll-post-embed]: https://raw.githubusercontent.com/MinnDevelopment/fxreddit/master/assets/poll-post-embed.png

# FixReddit

Provides improved reddit embeds for services such as Discord.

This is a fork by [seriaati](https://github.com/seriaati) that will continue to receive bug fixes and new features for the original project, [fxreddit](https://github.com/MinnDevelopment/fxreddit) by [MinnDevelopment](https://github.com/MinnDevelopment), for the purposes of [Embed Fixer](https://ef.seria.moe).

Currently, on top of the original project, this fork adds:
- Discord component embeds
- YouTube video playback through [Koutube](https://github.com/iGerman00/koutube)
- And several other bug fixes

## About

This app is a cloudflare worker service which proxies links for reddit posts and transforms them into [Open Graph](https://ogp.me/) and [Twitter Cards](https://developer.twitter.com/en/docs/twitter-for-websites/cards/overview/markup) meta data for unfurlers.

The main instance is currently hosted on `https://fxreddit.seria.moe`.

## Example Embeds

This has specialized handling for various types of reddit posts.

The currently supported routes are:

| Route                                       | Example                                                                                                          |
|---------------------------------------------|------------------------------------------------------------------------------------------------------------------|
| `/r/:subreddit/comments/:id/:slug/:comment` | https://fxreddit.seria.moe/r/shittymoviedetails/comments/160onpq/breaking_actor_from_home_alone_2_arrested_today/jxnkq4g |
| `/r/:subreddit/comments/:id/:slug`          | https://fxreddit.seria.moe/r/shittymoviedetails/comments/160onpq/breaking_actor_from_home_alone_2_arrested_today         |
| `/r/:subreddit/comments/:id`                | https://fxreddit.seria.moer/shittymoviedetails/comments/160onpq                                                         |
| `/r/:subreddit/s/:id`                       | https://fxreddit.seria.moe/r/MemePiece/s/15w6vzg82W                                                                      |
| `/:id`                                      | https://fxreddit.seria.moe/160onpq                                                                                       |

Or replacing `/r/` with `/u/` and `/user/` for profile posts.

Because this fork is mainly made for [Embed Fixer](https://ef.seria.moe), the URLs are difficult to be replaces manually, using Embed Fixer is recommended.

### Image Posts

An image post is a reddit post with just an uploaded image. This provides the title and image as a large image card.

![image post embed][image-post-embed]

### Gallery Posts

A gallery post is a reddit post with multiple attached images. Since Discord can only show a up to four images for link embeds, the description includes a tag line that indicates the total number of images.

![gallery post embed][gallery-post-embed]

### Video Posts

A video post works exactly like an image post, except for providing a video instead.

![video post embed][video-post-embed]

### YouTube Posts

A YouTube post is a video post that links to a youtube video. The service will instead provide a link to the embed iframe, which can be handled by Discord as a youtube iframe instead. This also includes clips!

![youtube post embed][youtube-post-embed]

### Article Posts

Article posts are simply external links, and sometimes provide a thumbnail.

![article post embed][article-post-embed]

### Tweet Posts

Tweet posts are links to tweets, which might include images or videos and text content.

![tweet post embed][tweet-post-embed]

### Twitch Posts

Twitch posts are links to twitch clips or VODs.

![twitch post embed][twitch-post-embed]

### Poll Posts

Polls including votes (once finished).

![poll embed][poll-post-embed]
