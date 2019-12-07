from flask import render_template, redirect, request, url_for, flash, current_app
from . import forum
from flask_login import login_user, login_required, logout_user, current_user
from ..models import Permission, Patient, User, Hospital, Forum, Forum_members, ForumPermission, Post, Likes, Reaction, Top_forums, Top_posts, Task, Forum_profile, Forum_role
from ..email import send_email
from .. import db
from ..decorators import permission_required
from datetime import date
from datetime import datetime
from dateutil.relativedelta import relativedelta
from .forms import PostForm
import re
from flask import Flask

@forum.route('/home',  methods = ['GET','POST'])
@login_required
def home():
    update_forum()
    update_posts()
    top_f = db.session.query(Top_forums, Forum).join(Forum, (Top_forums.forum_id == Forum.forum_id)).filter(Top_forums.forum_id == Forum.forum_id).order_by(Top_forums.subscribers.desc()).limit(8).all()
    print(top_f)
    top_p = db.session.query(Top_posts, Post, Forum_profile).join(Post, Top_posts.post_id == Post.post_id).join(Forum_profile, Post.user_id == Forum_profile.user_id).order_by(Post.date_posted.desc()).all()
    forum_pro = Forum_profile.query.filter(Forum_profile.user_id == current_user.user_id)
    user_forums = db.session.query(Forum_members, Forum).join(Forum, Forum_members.forum_id == Forum.forum_id).filter(Forum_members.user_id == current_user.user_id).all()
    return render_template('forum/home.html', top_f = top_f, top_p = top_p, forum_pro = forum_pro, user_forums = user_forums)

def update_forum():
    update_f_task = Task.query.filter(Task.name == "update_forum").first()
    print(update_f_task)
    if update_f_task:
        if update_f_task.time_requested < datetime.utcnow() - relativedelta(hours = 24):
            current_user.launch_task(name = 'update_forum', description = 'Updating Top Forums')
    else:
        current_user.launch_task(name = 'update_forum', description = 'Updating Top Forums')
        print('adding_task')
    db.session.commit()

def update_posts():
    update_p_task = Task.query.filter(Task.name == "update_posts").first()
    print(update_p_task)
    if update_p_task:
        if update_p_task.time_requested < datetime.utcnow() - relativedelta(minutes = 1):
            current_user.launch_task(name = 'update_posts', description = 'Updating Top Posts')
    else:
        current_user.launch_task(name = 'update_posts', description = 'Updating Top Posts')
        print('adding_task')
    db.session.commit()

# @forum.route('/forums', methods = ['GET', 'POST'])
# def forums():
#
#     return

@forum.route('/profile', methods = ['GET', 'POST'])
def profile():
    #Returns recent comments, recent posts, recent likes, bio_link,
    posted_posts = Post.query.filter(Post.user_id == current_user.user_id).order_by(Post.date_posted.desc()).all()
    liked_posts = Likes.query.join(Post, (Likes.post_id == Post.post_id)).filter(Likes.user_id == current_user.user_id) \
                                .order_by(Likes.date_liked.desc()).all()
    reaction_posts = Reaction.query.join(Post, (Reaction.post_id == Post.post_id)).filter(Reaction.user_id == current_user.user_id) \
                                    .order_by(Reaction.date_commented.desc()).all()
    user_attributes = User.query.filter(User.user_id == current_user.user_id).first()
    forum_pro = Forum_profile.query.filter(Forum_profile.user_id == current_user.user_id)
    #In order to access profile, you need to href for images, which will be a static path
    if request.method == "Post":
        if request.form.get('new_bio'):
            new_bio = request.form['new_bio']
            profile = Forum_profile.query.filter(Forum.user_id == current_user.user_id).first()
            profile.bio = new_bio
            db.session.commit()
        elif request.files['file']:
            profile_upload(request, current_user.user_id)
        return render_template('forum/profile.html', posted_posts = posted_posts, liked_posts = liked_posts, reaction_posts = reaction_posts, user_attributes = user_attributes, forum_pro = forum_pro)
    return render_template('forum/profile.html', posted_posts = posted_posts, liked_posts = liked_posts, reaction_posts = reaction_posts, user_attributes = user_attributes, forum_pro = forum_pro)

def profile_upload(req, user_id):
    UPLOAD_FOLDER = "app/templates/files_uploaded/"
    USER_FOLDER = "profile/{}/".format(user_id)
    print("Request Files", request.files)
    f = req.files['file']
    try:
        f.save(os.path.join(UPLOAD_FOLDER, USER_FOLDER, secure_filename("icon.png")))
    except FileNotFoundError:
        print("Encountered a FileNotFoundError, creating a file >>> ", USER_FOLDER)
        os.mkdir(os.path.join(UPLOAD_FOLDER, USER_FOLDER))
        f.save(os.path.join(UPLOAD_FOLDER, USER_FOLDER, secure_filename("icon.png")))
    files=os.listdir(os.path.join(UPLOAD_FOLDER, USER_FOLDER))

@forum.route('/hh/<forum_name>', methods = ['GET', 'POST'])
def page(forum_name):
    curr_forum = Forum.query.filter(Forum.forum_name == forum_name).first()
    form = PostForm()
    if curr_forum:
        forum_members = Forum_members.query.filter(Forum_members.forum_id == curr_forum.forum_id).all()
        # Sub_query = Likes.query.with_entities((Likes.post_id), db.func.count(Likes.user_id)).group_by(Likes.post_id).subquery()
        forum_posts = db.session.query(Post, Likes, Forum_profile) \
                                .filter(Post.forum_id == curr_forum.forum_id) \
                                .outerjoin(Likes, (Post.post_id == Likes.post_id)) \
                                .join(Forum_profile, (Forum_profile.user_id == Post.user_id)) \
                                .with_entities(Post.forum_id, Post.post_id, Post.content, Forum_profile.username, db.func.count(Likes.user_id)) \
                                .group_by(Post.post_id).order_by(Post.date_posted.desc()).all()
                                # .all()
        print(curr_forum.forum_id)
        # print(forum_posts.all())
        if current_user.user_id in [i.user_id for i in forum_members]:
            subscribed = True
        else:
            subscribed = False
        if form.validate_on_submit():
            text = form.text.data
            # text = request.form.get('new_post')
            new_post = Post(forum_id = curr_forum.forum_id,
                            date_posted = datetime.now(),
                            user_id = current_user.user_id,
                            content = text)
            db.session.add(new_post)
            db.session.commit()
            flash('Post Submitted')
            return redirect(url_for('forum.page', forum_name = forum_name))
        else:
            # flash('Invalid Post')
            return render_template('forum/page.html', form = form, curr_forum = curr_forum, forum_members = forum_members, forum_posts = forum_posts, subscribed = subscribed)
        if request.method == "POST":
            if request.form['subscribe_button'] == 'subscribe':
                subscription = Forum_members(forum_id = curr_forum.forum_id,
                                            user_id = current_user.user_id,
                                            role_id = Role.query.filter_by(default = True).first())
                db.session.add(subscription)
                db.session.commit()
                subscribed = True
                flash('You have successfully subscribed')
                return render_template('forum/page.html', form = form, curr_forum = curr_forum, forum_members = forum_members, forum_posts = forum_posts, subscribed = subscribed)
            elif request.form['subscribe_button'] == 'unsubscribe':
                Forum_members.query.filter((Forum_members.forum_id == curr_forum) & (Forum_members.user_id == current_user.user_id)).delete()
                db.session.commit()
                subscribed = False
                flash('You have been successfully unsubscribed')
                return render_template('forum/page.html', form = form, curr_forum = curr_forum, forum_members = forum_members, forum_posts = forum_posts, subscribed = subscribed)
    else:
        flash('Invalid Forum Route')
        return redirect(url_for('forum.home'))
