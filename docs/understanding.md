Hey see below is the main resource of what needs to be done, and my understanding, other than this anything else if I gave you it's to get to you know what's happening with other's and which are announcements in the classroom

Hey mentor said to understand what this project is about and then, write what you think to solve,
implement in simple english in understandable way, he strictly warned don't to use AI to generate the understanding 
report which I am going to write now, so he said like first a simple 2/3 paragraphs which says what you understand about this project, and next what you are thinking to implement in this project, then a clear thing of use casses, and all, then think in terms of customer's so that it becomes easy to understand the motive , usecases then features, and think interms of customer, make their life easy,  also we shouldn't 
don't just add features justify everything why added, and why it's relavent and useful, so I we need to first work on 
the imp features/things, I mean necessary and imp stuff, first, must do kind of thing, then if time permits like that some less imp features. 


So pasting below what is the problem statement that was actually given by sir, so from that we have to do whatever we think is proper to do, so it's on us how we proceed, so that's what our main focus in on

14	ShopSense — Customer Care & Order Operations Assistant: Develop a multi-agent AI assistant for customer support, order management, refunds, and policy-based decision making.		Implementation + Experiments — Build a customer-care assistant covering ticket triage, order/refund tools, customer memory, policy RAG, LangGraph orchestration, MCP integration, observability/reliability, and end-to-end evaluation with refund and prompt-injection guardrails.	Animesh



My understanding - hey this is vauge I am just writing it down what I am thinking so, help me if my way of thinking is wrong. 
So there is a mock e-commerce website or something(since our main focus is developing AI assistant) so to this website, we will build a multi agent AI assistant, where it can lets first focus on 
1. Customer support - where it will help with any basic doubts related to his orders
2. Order Management - where if asks doubts/ or tells to do some stuff related to orders to do, so that agents has to split work based on what kind of work each agent does, and verify whether what he is telling actually correct or not, and also has to perform that task in the actual database and backend, and verify whether it happened or not, and need to inform him that it happened and also if anything is wrong need to tell him immediately that this is the problem, and this doesn't match from what you said like that, example cancel the order which I just placed if it not shipped yet, it's easy to cancel and easy to refund the money, if not we have to wait until it deliveries then we have to upload proper stuff, for the proofs under re-fund section, and wait for approval, and ... if he asks like tell me the total amount of stuff in my cart or total amount of stuff under this particular category in my cart, ...
2. Policy based decision making - So company have some policies, so we have to make sure to keep this in mind everytime, so that when user instructs to do any operation we have to make sure everything is under company policies only, and Identifying the type of request it is, first, 

Hey I just wrote whatever that came to my mind, I might have missed a lot of stuff, and wrote unnecessary stuff not relavent to what sir is expecting, and all, so help me to think in what he is expecting to go in the direction





So Starting writing it here for Assignment1 
# This project is a multi agent AI system which takes real irreversible actions on customer's money and order's based on the customer's words alone, without human approving each of the decision, and this multi agent system does it correctly following company policies every time even when the customer is confused, lying or trying to attach the system.

So this is not a basic chat bot kind of project cause that would become a simple retriveal problem, when it does things like issuing refund it becomes a real systems and safety problem.
So since the moment our agentic system takes action on real database and on our system, mistakes can cost money and trust from our customers. 

