you are forbidden from writing code or editing any files until you are explicitly told to do so. 

before writing any code, clearly state what the goal of the pass will be. any code that does not serve this goal must be removed. get approval on the goal of the pass before writing code. explain the implementation at a high level and how it achieves the goal before implementing. 

prefer the minimum amount of code that still achieves the goal. 

you are forbidden from writing sentences that include any run-on or comparisons. no prose. 
you are forbidden from using em-dashes. 
you are forbidden from using metaphors. 

you are forbidden from using a technical term before it has been clearly introduced. you must explain all of your ideas without relying on a word or phrase that requires another explanation. 

challenge me on my ideas. my way of learning consists of making a bet/assumption out loud. it may be right or it may be wrong. call me out in both cases. we are learning together. building a shared understanding of the system together. 

always focus on the product being built. every pass should satisfy a product feature we are building. what does the user need? what is their workflow? how are we improving it? how are we making their lives easier? a lot of simplifications come from focusing on the product/user as opposed to the pure software system. 

# System philosophy

## Goal

Communicate artists' ideas through mixing choices.

## Theme

A great artist has a message to communicate. A perspective they want people to see the world through. An emotion they want people to feel. We call this the THEME.

## Knobs

Every medium gives an artist ways to communicate a theme. Painters have color, brush stroke, canvas size. Clothing designers have fabric, cut, distressing. We call these KNOBS.

A mix engineer's knobs come in a few kinds:
- **Balance:** how loud each part is next to the others.
- **Tone:** which pitches are strong or weak. Bright or dark, thin or heavy.
- **Space:** how near or far a sound feels. How big the room around it is.
- **Echo:** sounds repeating after they play.
- **Width:** where sounds sit from left to right. How wide the song feels.
- **Dynamics:** how far apart the quiet and loud moments are.
- **Texture:** clean and polished, or gritty and worn.
- **Movement:** sound that wobbles, shimmers, or swirls.
- **Change over time:** any knob moving during the song.

Each kind is turned through **controls**. A control is an exact effect, setting, and value in the artist's music software. Example: Reverb, Decay Time, 3 seconds. The kinds are few and fixed. The controls are fixed by the software, and there are thousands.

We mix. We do not master. Mastering is the final polish of a finished song as one file. Mixing shapes the parts inside a project.

## Coherence

Great art has a clear theme. Every choice in the medium is a chance to communicate it. The best art is coherent: all choices communicate the theme.

So every control the system sets must trace back to the theme.

## Core problem

Artists communicate a theme in many ways. Words, examples, stories, analogies, reference songs.

The controls are fixed.

The system goes from any unstructured input to which controls to turn, and by how much.

artist theme (raw, unstructured) -> which controls to turn, by how much

## Artist language is not fixed

Different artists use different words for the same sound. The same word means different sounds to different artists. There is no correct word for a sound.

So the system adapts to each artist. No fixed word-to-control tables, in code or in instructions to the LLM. Knowledge given to the LLM is examples and explanations to reason from. It is never rules.

A human engineer has shared experience and body language to understand an artist. This system has only words. The LLM's reasoning and questions carry that load.

## Levels

Levels describe how specific a piece of artist input is.
- **High:** a theme, story, analogy, or reference. "I want this to feel melancholic."
- **Middle:** a part of the song and a kind of knob. "Make the voice sound far away."
- **Low:** a control. "More reverb on the vocal."

Artists will speak at every level, often in one message. Lower levels need fewer translation steps. The theme still decides how every piece is carried out.

## Architecture

There are two boxes:

raw artist input -> LLM box -> controls -> core box -> instructions to the artist's music software

**LLM box.** All the thinking. It interprets the artist, asks questions, and chooses controls. It is exploratory and creative. Different techniques steer it while letting it experiment. This is where the value is, and where we experiment.

**Core box.** Mechanical plumbing. It adapts controls to whatever music software the artist uses. It converts units, adds or changes effects, and rejects what the software cannot do. It holds no taste and makes no creative decisions. Keep it as small as possible. One exception: a hard volume limit for safety.

A change that adds judgment to the core box is wrong by default. Improvement happens in the LLM box.

## Feedback

Tinkering is a large part of the creative process. Trying a knob, a setting, or a combination, and hearing what works.

So the first attempt does not need to be perfect. The feedback path must work. The artist listens and reacts. The LLM box adjusts from the current state. It does not start over.

Every change to the LLM box is checked against a fixed set of test inputs, judged by ear. Without that, we cannot tell if a change helped.

# Vocabulary

Shared vocabulary is crucial for human-agent communication. Below are the words we will use and the meanings we have agreed on. This list will continue to grow.

**Product**
- **Theme:** the message, perspective, or emotion an artist wants to communicate.
- **Knobs:** the ways a medium lets an artist communicate a theme.
- **Knob kinds:** the few kinds of knobs a mix engineer has. Balance, tone, space, echo, width, dynamics, texture, movement, change over time.
- **Controls:** the exact effect, setting, and value in the DAW. Example: Reverb, Decay Time, 3 seconds.
- **Coherence:** every choice communicates the theme.
- **Mix:** shaping the parts inside a project. This is what we do.
- **Master:** the final polish of a finished song as one file. This is not what we do.

**Artist input**
- **Levels:** how specific a piece of artist input is.
- **High level:** a theme, story, analogy, or reference. "I want this to feel melancholic."
- **Middle level:** a part of the song and a knob kind. "Make the voice sound far away."
- **Low level:** a control. "More reverb on the vocal."