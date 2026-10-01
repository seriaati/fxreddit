export interface RedditListingData {
    id: string;
    subreddit: string;
    permalink: string;
    title: string;
    author: string;
    original_author?: string;
    is_comment?: boolean;
    post_hint?: string; // 'image' | 'hosted:video'
    url: string;
    selftext?: string; // content in posts
    body?: string; // content in comments
    is_reddit_media_domain: boolean;
    media_only?: boolean;
    num_comments?: number; // number of comments
    domain?: string;
    thumbnail?: string;
    thumbnail_width?: number;
    thumbnail_height?: number;
    replies?: RedditListingResponse;
    media?: RedditMedia;
    preview?: {
        images?: {
            source?: { url: string, width: number, height: number };
            resolutions: { url: string, width: number, height: number }[];
        }[]
    };
    secure_media?: RedditMedia;
    secure_media_embed?: {
        media_domain_url: string;
        width: number;
        height: number;
    };
    media_metadata?: Record<string, {
        e?: string; // 'Image' | 'AnimatedImage'
        s?: {
            y: number; // height
            x: number; // width
            u?: string; // missing on animated images
            gif?: string;
            mp4?: string;
        };
    } | undefined>;
    gallery_data?: {
        items: [{
            caption?: string,
            media_id: string
        }]
    };
    poll_data?: PollData;
    crosspost_parent_list?: RedditListingData[];
    // Used by the component embed
    created_utc?: number;
    edited?: number | false;
    score?: number;
    upvote_ratio?: number;
    over_18?: boolean;
    spoiler?: boolean;
    locked?: boolean;
    stickied?: boolean;
    link_flair_text?: string | null;
    is_original_content?: boolean;
    distinguished?: string | null;
    is_submitter?: boolean;
    removed_by_category?: string | null;
    sr_detail?: { community_icon?: string | null; icon_img?: string | null } | null; // requested with ?sr_detail=1
}

export interface RedditMedia {
    reddit_video?: {
        fallback_url: string;
        height: number;
        width: number;
        has_audio: boolean;
    };
    oembed?: RedditMediaOEmbed;
    type?: string; // "youtube"
}

export interface RedditMediaOEmbed {
    thumbnail_url: string;
    thumbnail_width: number;
    thumbnail_height: number;
    width: number;
    height: number;
    title: string;
}

export interface RedditListingResponse {
    kind: string; // 'Listing'
    data: {
        children: {
            kind: string; // 't3'
            data: RedditListingData;
        }[];
    };
}

export interface RedditPost {
    subreddit: string;
    title: string;
    author: string;
    comment?: RedditPost;
    post_hint: string; // 'image'
    url: string;
    permalink: string;
    description: string;
    is_reddit_media: boolean;
    is_media_only: boolean;
    preview_image_url?: string;
    domain?: string;
    resolution?: {
        width: number;
        height: number;
    };
    video_url?: string;
    video_has_audio?: boolean;
    oembed?: {
        thumbnail_url: string;
        thumbnail_width: number;
        thumbnail_height: number;
        width: number;
        height: number;
        title: string;
    };
    media_metadata?: Image[];
    secure_media_embed?: {
        media_domain_url: string;
        width: number;
        height: number;
    };
    poll_data?: PollData;
    // Used by the component embed
    id?: string;
    created_utc?: number;
    edited?: boolean;
    score?: number;
    upvote_ratio?: number;
    num_comments?: number;
    nsfw?: boolean;
    spoiler?: boolean;
    locked?: boolean;
    stickied?: boolean;
    flair?: string;
    is_original_content?: boolean;
    distinguished?: string;
    is_submitter?: boolean;
    removed?: boolean;
    subreddit_icon?: string;
    media?: MediaItem[]; // ordered images and videos, URLs unescaped
    crosspost?: RedditPost;
}

export interface MediaItem {
    kind: 'image' | 'video';
    url: string;
    caption?: string;
}

export interface Image {
    url: string;
    width: number;
    height: number;
    caption?: string;
}

export interface PollData {
    total_vote_count: number;
    voting_end_timestamp: number;
    options?: PollDataOption[];
}

export interface PollDataOption {
    text: string;
    vote_count?: number;
}